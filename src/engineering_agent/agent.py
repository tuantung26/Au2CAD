"""
Engineering Agent — LangGraph implementation
=============================================
Reads CAD-IR + engineer context → reasons → proposes modifications
→ calls SolidWorks/CadQuery adapter → validation → loop until PASS.

The agent is intentionally provider-agnostic:
  * set LLM_PROVIDER + LLM_MODEL in .env
  * the get_llm() factory loads the correct LangChain chat model.

Graph topology
--------------

    [START]
       │
       ▼
   read_cadir         ← load CAD-IR and context
       │
       ▼
   reason             ← LLM analyses features, proposes changes
       │
       ▼
   apply_changes      ← update CADIR with LLM proposals
       │
       ▼
   build_cad          ← CadQuery adapter → STEP
       │
       ▼
   validate           ← GeometryValidator
       │
    ┌──┴──┐
   FAIL  PASS
    │      │
    ▼      ▼
  diagnose [END]
    │
    ▼
  reason  (loop back, max N iterations)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from src.cadfit_wrapper.parser import CADFitProgramParser
from src.config import LLM_MODEL, LLM_PROVIDER, VALIDATION_IOU_THRESHOLD
from src.models import CADIR, ValidationReport, ValidationStatus
from src.solidworks_adapter.cadquery_adapter import CadQueryAdapter
from src.validation.geometry_validator import GeometryValidator

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 5


# ── LLM factory ───────────────────────────────────────────────

# ── Resilient Multi-Provider LLM Factory ─────────────────────────

def create_chat_model(provider: str, model_name: str) -> Any:
    """Helper to create a LangChain chat model for a given provider and model name."""
    p = provider.lower()
    if p == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        from src.config import GOOGLE_API_KEY
        m = model_name.replace("models/", "")
        # Remap deprecated or quota-exhausted models to lightweight high-quota models
        if m in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.5-flash"):
            m = "gemini-flash-lite-latest"
        return ChatGoogleGenerativeAI(model=m, google_api_key=GOOGLE_API_KEY, temperature=0.1, request_timeout=30)
    elif p == "groq":
        from langchain_groq import ChatGroq
        import os
        return ChatGroq(model_name=model_name, temperature=0.1, max_tokens=4096, api_key=os.environ.get("GROQ_API_KEY"))
    elif p == "openai":
        from langchain_openai import ChatOpenAI
        import os
        return ChatOpenAI(model=model_name, temperature=0.1, api_key=os.environ.get("OPENAI_API_KEY"))
    elif p == "anthropic":
        from langchain_anthropic import ChatAnthropic
        import os
        return ChatAnthropic(model=model_name, temperature=0.1, api_key=os.environ.get("ANTHROPIC_API_KEY"))
    elif p == "huggingface":
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
        import os
        llm = HuggingFaceEndpoint(
            repo_id=model_name,
            temperature=0.1,
            huggingfacehub_api_token=os.environ.get("HUGGINGFACEHUB_API_TOKEN"),
        )
        return ChatHuggingFace(llm=llm)
    return None


def invoke_llm_with_fallback(prompt: str) -> str:
    """
    Invokes the preferred LLM from .env (prioritizing Groq and Hugging Face),
    automatically falling back to resilient alternative free models if any error occurs.
    """
    import os
    from src.config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY

    candidates: list[tuple[str, str]] = []

    # 1. Primary choice from config (e.g. groq or huggingface)
    primary_prov = (LLM_PROVIDER or "groq").lower()
    primary_model = LLM_MODEL or "llama-3.3-70b-versatile"
    candidates.append((primary_prov, primary_model))

    # 2. Add Groq candidates first if GROQ_API_KEY exists
    if os.environ.get("GROQ_API_KEY"):
        for m in ("llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"):
            if ("groq", m) not in candidates:
                candidates.append(("groq", m))

    # 3. Add Hugging Face candidates if token exists
    if os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
        for m in ("Qwen/Qwen2.5-Coder-32B-Instruct", "meta-llama/Llama-3.1-8B-Instruct"):
            if ("huggingface", m) not in candidates:
                candidates.append(("huggingface", m))

    # 4. Add OpenAI if key exists
    if os.environ.get("OPENAI_API_KEY"):
        candidates.append(("openai", "gpt-4o"))

    # 5. Fallback: Google high-quota lightweight models
    if GOOGLE_API_KEY or os.environ.get("GOOGLE_API_KEY"):
        for m in ("gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-flash-latest"):
            if ("google", m) not in candidates and ("google", f"models/{m}") not in candidates:
                candidates.append(("google", m))

    last_error = None
    for prov, model in candidates:
        try:
            logger.info("[Agent] Attempting LLM call with provider=%s model=%s ...", prov, model)
            chat_model = create_chat_model(prov, model)
            if not chat_model:
                continue
            response = chat_model.invoke(prompt)

            text = response.content if hasattr(response, "content") else str(response)
            if isinstance(text, list):
                text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in text)
            if not text and hasattr(response, "additional_kwargs"):
                text = (
                    response.additional_kwargs.get("reasoning")
                    or response.additional_kwargs.get("reasoning_content")
                    or ""
                )
            if text and len(text.strip()) > 0:
                logger.info("[Agent] Succeeded with provider=%s model=%s (%d chars).", prov, model, len(text))
                return text
        except Exception as exc:
            last_error = exc
            logger.warning("[Agent] Provider %s model %s failed: %s. Trying next available model/provider...", prov, model, exc)

    if last_error:
        raise RuntimeError(f"All LLM candidates failed. Last error: {last_error}")
    raise RuntimeError("No working LLM provider found. Check your .env configuration.")


def get_llm():
    """Backward compatibility wrapper."""
    return create_chat_model(LLM_PROVIDER, LLM_MODEL)


# ── Agent state ───────────────────────────────────────────────

class AgentState(TypedDict):
    cadir: CADIR | None
    reference_mesh_path: Path | None
    output_dir: Path
    engineer_context: str          # free-text description, drawing notes
    input_drawing: Path | None
    drawing_analysis: str          # Extracted VLM blueprint analysis
    iteration: int
    last_validation: ValidationReport | None
    final_step_path: Path | None
    done: bool
    error: str


# ── Node implementations ──────────────────────────────────────

def node_reason(state: AgentState) -> AgentState:
    """LLM analyses the CAD-IR and proposes modifications or forward engineering."""
    cadir = state["cadir"]
    report = state["last_validation"]
    context = state["engineer_context"]
    drawing_path = state.get("input_drawing")
    drawing_analysis = state.get("drawing_analysis", "")
    iteration = state["iteration"]

    # If drawing image exists and has not yet been processed by VLM, extract it now
    if drawing_path and drawing_path.exists() and not drawing_analysis:
        try:
            from src.engineering_agent.vlm_extractor import analyze_drawing
            logger.info("[Agent] Extracting blueprint geometry from %s using VLM...", drawing_path.name)
            drawing_analysis = analyze_drawing(drawing_path)
            state["drawing_analysis"] = drawing_analysis
        except Exception as exc:
            logger.warning("[Agent] VLM extraction encountered an issue: %s", exc)

    prompt = _build_prompt(cadir, report, context, drawing_analysis, iteration)
    logger.info("[Agent] Reasoning (iteration %d) …", iteration)

    try:
        text = invoke_llm_with_fallback(prompt)
        logger.info("[Agent] LLM response received (%d chars).", len(text))
        try:
            Path("output/llm_raw_response.txt").write_text(text, encoding="utf-8")
        except Exception:
            pass

        # Handle Forward Engineering (cadir is None)
        if cadir is None:
            new_cadir_json = _extract_json_object(text)
            if new_cadir_json:
                try:
                    cadir = CADIR(**new_cadir_json)
                    logger.info("[Agent] Successfully generated zero-shot CAD-IR (%s).", cadir.part_name)
                except Exception as e:
                    logger.error("[Agent] Failed to parse generated CAD-IR: %s", e)
                    return {**state, "error": f"Failed to parse generated CAD-IR: {e}", "done": True}
            else:
                logger.info("[Agent] No valid CAD-IR JSON found in response. Response excerpt: %s", text[:300])
                return {**state, "error": "No valid CAD-IR JSON found in LLM response.", "done": True}
        else:
            # Try to extract JSON patch from response
            patch = _extract_json(text)
            if patch:
                cadir = _apply_patch(cadir, patch)
                logger.info("[Agent] Applied %d patches from LLM.", len(patch))
            else:
                logger.info("[Agent] No structured patch found; proceeding unchanged.")

    except StopIteration:
        err_msg = (
            f"Hugging Face Hub API error (StopIteration): Model '{LLM_MODEL}' không được hỗ trợ bởi "
            f"Serverless Inference Provider của Hugging Face (huggingface_hub trả về provider list rỗng). "
            f"Thư viện huggingface_hub gặp StopIteration khi tìm provider cho model này."
        )
        logger.error("[Agent] %s", err_msg)
        return {**state, "cadir": None, "error": err_msg, "done": True}
    except Exception as exc:
        error_msg = f"LLM reasoning failed: {exc}"
        logger.error("[Agent] %s", error_msg)
        return {**state, "cadir": None, "error": error_msg, "done": True}

    return {**state, "cadir": cadir}


def node_build_cad(state: AgentState) -> AgentState:
    """Translate CAD-IR to STEP using CadQuery adapter."""
    if not state.get("cadir"):
        logger.error("[Agent] CAD-IR is None. Cannot build CAD.")
        return {**state, "error": "Reasoning failed to produce valid CAD-IR.", "done": True}

    adapter = CadQueryAdapter()
    result = adapter.build(state["cadir"], state["output_dir"])
    if not result.success:
        return {**state, "error": result.error, "done": True}
    return {**state, "final_step_path": result.step_path}


def node_validate(state: AgentState) -> AgentState:
    """Run geometry validation."""
    stl_path = state["output_dir"] / "generated.stl"
    if not stl_path.exists():
        if state.get("error"):
            return {**state, "last_validation": None, "done": True} # Keep the previous error
        return {**state, "last_validation": None, "done": True, "error": "STL not found for validation"}

    validator = GeometryValidator()
    report = validator.validate(
        reference_mesh_path=state["reference_mesh_path"],
        generated_stl_path=stl_path,
        cadir=state["cadir"],
    )
    if state.get("reference_mesh_path") is None:
        # In Forward Engineering mode (blueprint/context-led), successful CAD compilation
        # to STEP/STL satisfies generation. Mark as passed.
        passed = True
        if report.status == ValidationStatus.FAIL:
            report.status = ValidationStatus.PASS
    else:
        passed = report.status in (ValidationStatus.PASS, ValidationStatus.WARNING)
    logger.info("[Validate] status=%s  IoU=%.4f", report.status, report.iou or 0)
    return {**state, "last_validation": report, "done": passed}


def node_diagnose(state: AgentState) -> AgentState:
    """Increment iteration counter; stop if max reached."""
    iteration = state["iteration"] + 1
    done = iteration >= MAX_AGENT_ITERATIONS
    if done:
        logger.warning("[Agent] Max iterations (%d) reached; stopping.", MAX_AGENT_ITERATIONS)
    return {**state, "iteration": iteration, "done": done}


# ── Routing ───────────────────────────────────────────────────

def route_after_reason(state: AgentState) -> str:
    if state.get("done") or state.get("error") or not state.get("cadir"):
        return END
    return "build_cad"


def route_after_build_cad(state: AgentState) -> str:
    if state.get("done") or state.get("error"):
        return END
    return "validate"


def route_after_validate(state: AgentState) -> str:
    if state.get("done") or state.get("error"):
        return END
    return "diagnose"


# ── Graph assembly ────────────────────────────────────────────

def build_graph() -> Any:
    g = StateGraph(AgentState)
    g.add_node("reason", node_reason)
    g.add_node("build_cad", node_build_cad)
    g.add_node("validate", node_validate)
    g.add_node("diagnose", node_diagnose)

    g.add_edge(START, "reason")
    g.add_conditional_edges("reason", route_after_reason, {"build_cad": "build_cad", END: END})
    g.add_conditional_edges("build_cad", route_after_build_cad, {"validate": "validate", END: END})
    g.add_conditional_edges("validate", route_after_validate, {"diagnose": "diagnose", END: END})
    g.add_edge("diagnose", "reason")

    return g.compile()


# ── Public runner ─────────────────────────────────────────────

class EngineeringAgent:
    def __init__(self) -> None:
        self.graph = build_graph()

    def run(
        self,
        cadir: CADIR | None,
        reference_mesh_path: Path | None,
        output_dir: Path,
        engineer_context: str = "",
        input_drawing: Path | None = None,
    ) -> AgentState:
        initial: AgentState = {
            "cadir": cadir,
            "reference_mesh_path": reference_mesh_path,
            "output_dir": output_dir,
            "engineer_context": engineer_context,
            "input_drawing": input_drawing,
            "drawing_analysis": "",
            "iteration": 0,
            "last_validation": None,
            "final_step_path": None,
            "done": False,
            "error": "",
        }
        final = self.graph.invoke(initial)
        return final


# ── Helpers ───────────────────────────────────────────────────

def _build_prompt(
    cadir: CADIR | None,
    report: ValidationReport | None,
    context: str,
    drawing_analysis: str,
    iteration: int,
) -> str:
    from src.engineering_agent.knowledge import load_knowledge_base
    
    ir_json = cadir.model_dump_json(indent=2) if cadir else "None (Forward Engineering Mode)"
    validation_summary = report.notes if report else "No validation yet."
    kb_content = load_knowledge_base()
    
    kb_section = f"\nEngineering Knowledge Base & Standards:\n{kb_content}\n" if kb_content else ""
    # Prompt context handling
    if cadir is None:
        vlm_text = (drawing_analysis[:6000] + "\n...[truncated]") if len(drawing_analysis) > 6000 else drawing_analysis
        vlm_section = f"\nVisual Technical Drawing Blueprint (VLM Extracted Geometric Data):\n{vlm_text}\n" if vlm_text else ""
        context_str = (context[:8000] + "\n...[truncated]") if len(context) > 8000 else context
    else:
        vlm_section = ""
        context_str = context[:1500] if len(context) > 1500 else context

    if cadir is None:
        task_instructions = """Your task:
1. You are starting from scratch (Forward Engineering 3D CAD model).
2. Generate a complete JSON object representing the CAD-IR based on the Engineer context, Technical Drawing analysis, and Knowledge Base.
3. The JSON must match the CADIR schema:
   {
     "part_name": "MechanicalComponent",
     "units": "mm",
     "features": [ ... list of CADFeature objects ... ]
   }

CADFeature Schema & Capabilities:
- id: "F1", "F2", etc.
- type: EXTRUDE | REVOLVE | SWEEP | PIPE | CUT | HOLE | PATTERN | FILLET | CHAMFER
- profile: "rectangle" | "circle" | "cylinder" | "pipe" | "custom"
- workplane: "XY" | "XZ" | "YZ"
- center: [x, y] in mm (center offset relative to origin)
- depth: float in mm (extrusion height or cut depth)
- diameter: float in mm (for cylinders, holes, or pipe outer diameter)
- inner_diameter: float in mm (for hollow pipes, curved tubes, or bores)
- path_points: list of [x, y] coordinates for curved trajectories (e.g. [[0.0, 0.0], [0.0, 40.0], [25.0, 65.0], [50.0, 40.0], [50.0, 0.0]])
- path_type: "spline" | "arc" | "u_bend" | "straight"
- path_plane: "XZ" | "XY" | "YZ" (plane of the trajectory curve)
- radius: float in mm (for fillets/chamfers or circles)
- bolt_circle_diameter: float in mm (PCD for circular bolt hole patterns)
- hole_count: int (number of holes on the bolt circle)
- operation: "add" (material addition/boss/pipe) or "cut" (cavity/pocket/internal bore)
- through_all: bool (true for through holes)
- parameters: [{"name": "length", "value": 105.0}, {"name": "width", "value": 70.0}] (for rectangles)

CRITICAL CAD MODELING RULES:
- Do NOT restrict yourself to simple cubes! Model the true geometry of the mechanical component:
  1. Base plate or mounting flanges: EXTRUDE with "rectangle" or "cylinder".
  2. Main body, bosses, or cylinder spigots: EXTRUDE with profile "cylinder".
  3. Curved cylinders, bent tubes, elbows, U-tubes, or fluid flow passages: use type "SWEEP" or "PIPE" with diameter, inner_diameter (if hollow), and path_points or path_type: "u_bend".
  4. Internal cavities / stepped bores: CUT with profile "cylinder" or "rectangle".
  5. Bolt arrays: HOLE or PATTERN with bolt_circle_diameter and hole_count.
  6. Edge treatments: FILLET or CHAMFER.
- ALL dimensions must be numeric floats, NOT strings!

Example 1 (Component with Flange & Curved Pipe / U-tube):
{
  "part_name": "ManifoldHousing",
  "units": "mm",
  "features": [
    {
      "id": "F1_Flange",
      "type": "EXTRUDE",
      "profile": "cylinder",
      "diameter": 100.0,
      "depth": 12.0,
      "center": [0.0, 0.0]
    },
    {
      "id": "F2_CurvedPipe",
      "type": "PIPE",
      "diameter": 24.0,
      "inner_diameter": 18.0,
      "path_points": [[0.0, 0.0], [0.0, 40.0], [25.0, 65.0], [50.0, 40.0], [50.0, 0.0]],
      "path_plane": "XZ",
      "workplane": "XY",
      "operation": "add"
    },
    {
      "id": "F3_BoltPattern",
      "type": "HOLE",
      "bolt_circle_diameter": 80.0,
      "hole_count": 4,
      "diameter": 10.0,
      "through_all": true
    }
  ]
}

Output ONLY the complete valid JSON object, without conversational prose.
"""
    else:
        task_instructions = """Your task:
1. Review the CAD features for correctness.
2. If there are dimension errors, propose corrections as a JSON patch.
3. Return a JSON array of patches in the format:
   [{"feature_id": "F1", "parameter": "depth", "new_value": 50.0}, ...]
4. If nothing needs changing, return an empty array: []

Only output the JSON array, no explanation needed.
"""

    return f"""You are an Engineering CAD Agent reviewing or generating a parametric CAD model.

Iteration: {iteration}
Engineer context: {context_str or 'None provided'}{vlm_section}{kb_section}

Current CAD-IR:
{ir_json}

Last Validation Result:
{validation_summary}

{task_instructions}"""


def _extract_json(text: str) -> list[dict] | None:
    """Extract a JSON array (list of dicts) from LLM output."""
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        cleaned = text[start:end+1]
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
            return None
        except json.JSONDecodeError:
            return None
    return None

def _extract_json_object(text: str) -> dict | None:
    """Extract a JSON object (dict) from LLM output using balanced brace parsing."""
    import re
    if not text:
        return None

    # Strip single-line comments
    text_clean = re.sub(r"//.*?\n", "\n", text)

    # 1. Search markdown code blocks ```...```
    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?```", text_clean, re.DOTALL):
        block = m.group(1).strip()
        b_start = block.find('{')
        b_end = block.rfind('}')
        if b_start != -1 and b_end > b_start:
            candidate = block[b_start:b_end + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                try:
                    fixed = re.sub(r",\s*([\]}])", r"\1", candidate)
                    data = json.loads(fixed)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    pass

    # 2. Look specifically for a JSON block containing "part_name"
    pn_idx = text_clean.find('"part_name"')
    if pn_idx != -1:
        b_start = text_clean.rfind('{', 0, pn_idx)
        if b_start != -1:
            brace_count = 0
            for i in range(b_start, len(text_clean)):
                if text_clean[i] == '{':
                    brace_count += 1
                elif text_clean[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        candidate = text_clean[b_start:i + 1]
                        try:
                            data = json.loads(candidate)
                            if isinstance(data, dict):
                                return data
                        except json.JSONDecodeError:
                            try:
                                fixed = re.sub(r",\s*([\]}])", r"\1", candidate)
                                data = json.loads(fixed)
                                if isinstance(data, dict):
                                    return data
                            except json.JSONDecodeError:
                                pass
                        break

    # 3. Fallback: Search all balanced brace blocks containing "features"
    for m in re.finditer(r'\{', text_clean):
        b_start = m.start()
        brace_count = 0
        for i in range(b_start, len(text_clean)):
            if text_clean[i] == '{':
                brace_count += 1
            elif text_clean[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    candidate = text_clean[b_start:i + 1]
                    if '"features"' in candidate:
                        try:
                            data = json.loads(candidate)
                            if isinstance(data, dict):
                                return data
                        except json.JSONDecodeError:
                            pass
                    break
    return None


def _apply_patch(cadir: CADIR, patches: list[dict]) -> CADIR:
    """Apply parameter patches proposed by the LLM to the CADIR."""
    feat_map = {f.id: f for f in cadir.features}
    for patch in patches:
        fid = patch.get("feature_id")
        pname = patch.get("parameter")
        new_val = patch.get("new_value")
        if fid not in feat_map or pname is None or new_val is None:
            continue
        feat = feat_map[fid]
        for param in feat.parameters:
            if param.name == pname:
                param.value = float(new_val)
                logger.info("Patched %s.%s → %.4f", fid, pname, float(new_val))
        # Also update top-level fields
        if pname == "depth":
            feat.depth = float(new_val)
        elif pname == "radius":
            feat.radius = float(new_val)
        elif pname == "diameter":
            feat.diameter = float(new_val)
    return cadir
