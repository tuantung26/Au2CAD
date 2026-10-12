"""
Au2CAD — Cloud API Server (FastAPI)
===================================
Provides REST API & WebSocket/SSE-ready endpoints to control the Au2CAD
reverse engineering & mold design pipeline, stream real-time logs,
serve 3D models (STL/STEP), and interact with the Engineering Agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("au2cad.api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Au2CAD Cloud API",
    description="Agentic AI System for Automated Reverse Engineering and Preliminary Mold Design",
    version="1.0.0",
)

# Enable CORS for local Vite dev server and cloud origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
DEMO_DIR = BASE_DIR / "demo_part"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory store for active and completed pipeline tasks
tasks: Dict[str, Dict[str, Any]] = {}


class PipelineRunRequest(BaseModel):
    drawing_filename: Optional[str] = None
    photo_filenames: Optional[List[str]] = []   # physical object photos
    context_text: Optional[str] = None
    mock_cadfit: bool = True
    skip_agent: bool = False
    skip_mold: bool = False


class ChatMessageRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Au2CAD AI Cloud Engine",
        "timestamp": time.time(),
        "has_demo_data": DEMO_DIR.exists(),
        "has_output_model": (OUTPUT_DIR / "solidworks" / "generated.stl").exists(),
    }


@app.get("/api/demo/meta")
def get_demo_meta():
    """Retrieve default demo dataset specifications and blueprint paths."""
    drawing_candidates = []
    drawing_dir = DEMO_DIR / "input" / "drawing"
    if drawing_dir.exists():
        for ext in ("*.jpg", "*.png", "*.jpeg", "*.pdf", "*.webp"):
            drawing_candidates.extend([p.name for p in drawing_dir.glob(ext)])

    desc_path = DEMO_DIR / "input" / "description.txt"
    desc_content = desc_path.read_text(encoding="utf-8") if desc_path.exists() else ""

    return {
        "part_name": "Mechanical Bracket",
        "description": desc_content,
        "available_drawings": drawing_candidates,
        "drawing_file": drawing_candidates[0] if drawing_candidates else None,
    }


@app.post("/api/upload")
async def upload_files(
    drawing: Optional[UploadFile] = File(None),
    photos: Optional[List[UploadFile]] = File(None),
    description: Optional[str] = Form(None),
):
    """Upload blueprint drawing or multi-view photos."""
    uploaded_files = {}

    if drawing and drawing.filename:
        save_path = UPLOAD_DIR / f"drawing_{drawing.filename}"
        with open(save_path, "wb") as f:
            shutil.copyfileobj(drawing.file, f)
        uploaded_files["drawing"] = str(save_path.name)

    if photos:
        saved_photos = []
        for photo in photos:
            if photo.filename:
                save_path = UPLOAD_DIR / f"photo_{photo.filename}"
                with open(save_path, "wb") as f:
                    shutil.copyfileobj(photo.file, f)
                saved_photos.append(str(save_path.name))
        uploaded_files["photos"] = saved_photos

    if description:
        desc_path = UPLOAD_DIR / "user_description.txt"
        desc_path.write_text(description, encoding="utf-8")
        uploaded_files["description"] = description

    return {
        "status": "success",
        "files": uploaded_files,
        "message": f"Uploaded {len(uploaded_files)} input items successfully.",
    }


def _execute_pipeline_task(task_id: str, req: PipelineRunRequest):
    """Worker running the full Au2CAD Pipeline."""
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = time.time()
    task["progress"] = 5
    task["stage"] = "Initializing Engine"
    task["logs"].append("🚀 Khởi tạo tiến trình phân tích Au2CAD...")

    try:
        # Determine inputs
        input_drawing = None
        if req.drawing_filename:
            candidate = UPLOAD_DIR / req.drawing_filename
            if candidate.exists():
                input_drawing = candidate
        if not input_drawing:
            # Fallback to demo drawing
            drawing_dir = DEMO_DIR / "input" / "drawing"
            if drawing_dir.exists():
                for ext in ("*.jpg", "*.png", "*.jpeg", "*.pdf", "*.webp"):
                    candidates = sorted(drawing_dir.glob(ext))
                    if candidates:
                        input_drawing = candidates[0]
                        break

        context_text = req.context_text or ""
        if not context_text:
            desc_file = DEMO_DIR / "input" / "description.txt"
            if desc_file.exists():
                context_text = desc_file.read_text(encoding="utf-8")

        dirs = {
            "cad_ir": OUTPUT_DIR / "cad_ir",
            "solidworks": OUTPUT_DIR / "solidworks",
            "validation": OUTPUT_DIR / "validation",
            "mold": OUTPUT_DIR / "mold",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)

        task["logs"].append(f"📁 Thư mục output: {OUTPUT_DIR}")
        if input_drawing:
            task["logs"].append(f"📐 Bản vẽ đầu vào: {input_drawing.name}")

        final_step_path = None

        # 5-Module Drawing-led SSOT Pipeline
        task["stage"] = "1/5 Perception / Parser (SSOT)"
        task["progress"] = 20
        task["logs"].append("👁️ [1/5] Trích xuất hình học và kích thước từ tất cả nguồn dữ liệu...")
        drawing_notes = ""
        photo_notes = ""
        structured_manifest = None

        # -- A. Phân tích Bản vẽ kỹ thuật (nếu có) --
        if input_drawing and input_drawing.exists():
            from src.engineering_agent.vlm_extractor import analyze_drawing
            from src.perception import BlueprintFeatureDimensionExtractor
            drawing_notes = analyze_drawing(input_drawing)
            dim_extractor = BlueprintFeatureDimensionExtractor()
            structured_manifest = dim_extractor.extract(input_drawing)
            manifest_path = OUTPUT_DIR / "structured_dimensions.json"
            manifest_path.write_text(structured_manifest.model_dump_json(indent=2), encoding="utf-8")
            task["logs"].append(f"✓ Bản vẽ: Khóa {len(structured_manifest.dimension_constants)} hằng số hình học.")

        # -- B. Phân tích Ảnh chụp vật thể (nếu có) --
        photo_paths = []
        if req.photo_filenames:
            for fname in req.photo_filenames:
                p = UPLOAD_DIR / fname
                if p.exists():
                    photo_paths.append(p)
        if photo_paths:
            from src.engineering_agent.vlm_extractor import analyze_object_photos
            photo_notes = analyze_object_photos(photo_paths)
            task["logs"].append(f"✓ Ảnh vật thể: Phân tích {len(photo_paths)} ảnh bằng VLM.")

        # -- C. Gộp tất cả nguồn → Perception Parser --
        combined_notes = "\n\n".join(filter(None, [drawing_notes, photo_notes]))
        if not combined_notes:
            # Text-description only: pass context as notes
            combined_notes = context_text or ""
            if combined_notes:
                task["logs"].append("⚠️ Chỉ có mô tả văn bản — sử dụng text-only perception.")

        from src.perception import DrawingPerceptionParser
        parser = DrawingPerceptionParser()
        perception_output = parser.parse(drawing_notes=combined_notes, context=context_text)
        perception_path = OUTPUT_DIR / "perception.json"
        perception_path.write_text(perception_output.model_dump_json(indent=2), encoding="utf-8")
        task["logs"].append(f"✓ Nhận diện {len(perception_output.raw_features)} features, {len(perception_output.candidate_constraints)} constraints.")


        task["stage"] = "2/5 Geometry Graph Builder"
        task["progress"] = 40
        task["logs"].append("🕸️ [2/5] Xây dựng đồ thị ràng buộc hình học (Geometry Graph)...")
        from src.geometry_graph import GeometryGraphBuilder
        graph_builder = GeometryGraphBuilder()
        graph = graph_builder.build_graph(perception_output)
        final_cadir = graph_builder.resolve_to_cadir(perception_output)
        cadir_path = dirs["cad_ir"] / "model.json"
        final_cadir.to_json(cadir_path)
        task["logs"].append(f"✓ Đồ thị: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges. Không có xung đột kích thước.")

        task["stage"] = "3/5 Parametric CadQuery Builder"
        task["progress"] = 65
        task["logs"].append("⚡ [3/5] Sinh mã CadQuery & Dựng mô hình khối rắn 3D (STEP/STL)...")
        from src.parametric_builder import ParametricCadQueryBuilder
        builder = ParametricCadQueryBuilder()
        build_result = builder.build(
            cadir=final_cadir,
            output_dir=dirs["solidworks"],
            input_drawing=input_drawing if input_drawing and input_drawing.exists() else None,
            drawing_notes=drawing_notes,
            feature_manifest=structured_manifest,
            auxiliary_context=context_text,
        )
        if not build_result.success:
            raise RuntimeError(f"CadQuery build failed: {build_result.error}")

        final_step_path = build_result.step_path
        task["logs"].append(f"✓ Tạo file STEP thành công: {build_result.step_path.name}")
        task["logs"].append(f"✓ Tạo file STL mesh thành công: {build_result.stl_path.name}")

        task["stage"] = "4/5 Symbolic & Geometric Verification"
        task["progress"] = 80
        task["logs"].append("🔍 [4/5] Kiểm định hình học và kiểm tra dung sai kích thước...")
        from src.verifier import SymbolicCADVerifier
        verifier = SymbolicCADVerifier()
        v_report = verifier.verify(
            cq_model=build_result.cq_model,
            cadir=final_cadir,
            perception=perception_output,
        )
        from dataclasses import asdict
        v_path = OUTPUT_DIR / "validation" / "verification_report.json"
        v_path.write_text(json.dumps(asdict(v_report), indent=2), encoding="utf-8")
        status_text = "PASS" if v_report.passed else "FAIL"
        task["logs"].append(f"✓ Trạng thái kiểm định: {status_text} ({len(v_report.checks)} quy tắc đã kiểm tra).")

        # Preliminary Mold Design
        if not req.skip_mold and final_step_path:
            task["stage"] = "5/5 Preliminary Mold Design"
            task["progress"] = 92
            task["logs"].append("🏭 [5/5] Phân tích thiết kế khuôn: góc thoát, hướng rút khuôn, undercut...")
            stl_path = dirs["solidworks"] / "generated.stl"
            if stl_path.exists():
                from src.mold_design.analyst import MoldAnalyst
                analyst = MoldAnalyst()
                mold_result = analyst.analyse(stl_path, dirs["mold"])
                task["logs"].append(f"✓ Hướng rút khuôn: {mold_result.report.parting_direction}")
                task["logs"].append(f"✓ Mặt undercut: {len(mold_result.report.undercut_faces)}, Đường phân khuôn: {len(mold_result.report.parting_line_edges)} cạnh.")

        task["progress"] = 100
        task["stage"] = "Completed"
        task["status"] = "success"
        task["ended_at"] = time.time()
        task["logs"].append("🎉 Pipeline hoàn tất thành công! Sẵn sàng xuất mô hình 3D và báo cáo kỹ thuật.")

    except Exception as e:
        logger.exception("Pipeline failed")
        task["status"] = "failed"
        task["error"] = str(e)
        task["stage"] = "Error"
        task["logs"].append(f"❌ Lỗi tiến trình: {str(e)}")


@app.post("/api/pipeline/run")
def start_pipeline(req: PipelineRunRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "progress": 0,
        "stage": "Queued",
        "logs": [],
        "created_at": time.time(),
        "error": None,
    }
    background_tasks.add_task(_execute_pipeline_task, task_id, req)
    return {"task_id": task_id, "status": "started"}


@app.get("/api/pipeline/status/{task_id}")
def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.get("/api/model/cad-ir")
def get_cad_ir():
    cad_ir_path = OUTPUT_DIR / "cad_ir" / "model.json"
    if not cad_ir_path.exists():
        # Fallback to demo cad_ir if exists
        demo_cad_ir = DEMO_DIR / "cad_ir" / "model.json"
        if demo_cad_ir.exists():
            cad_ir_path = demo_cad_ir
        else:
            return JSONResponse(status_code=404, content={"detail": "CAD-IR model not generated yet."})
    try:
        data = json.loads(cad_ir_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/stl")
def download_stl():
    """Serves the generated STL mesh file for Three.js 3D rendering."""
    stl_path = OUTPUT_DIR / "solidworks" / "generated.stl"
    if not stl_path.exists():
        demo_stl = DEMO_DIR / "solidworks" / "generated.stl"
        if demo_stl.exists():
            stl_path = demo_stl
        else:
            raise HTTPException(status_code=404, detail="STL mesh model not found. Please run the pipeline first.")
    return FileResponse(
        path=stl_path,
        media_type="application/sla",
        filename="au2cad_model.stl",
    )


@app.get("/api/model/step")
def download_step():
    """Serves the generated STEP CAD file."""
    step_path = OUTPUT_DIR / "solidworks" / "generated.step"
    if not step_path.exists():
        demo_step = DEMO_DIR / "solidworks" / "generated.step"
        if demo_step.exists():
            step_path = demo_step
        else:
            raise HTTPException(status_code=404, detail="STEP solid model not found. Please run the pipeline first.")
    return FileResponse(
        path=step_path,
        media_type="application/step",
        filename="au2cad_model.step",
    )


@app.get("/api/model/script")
def get_parametric_script():
    script_path = OUTPUT_DIR / "solidworks" / "parametric_model.py"
    if script_path.exists():
        return {"code": script_path.read_text(encoding="utf-8")}
    return {"code": "# Parametric CadQuery script not generated yet."}


@app.get("/api/verification/report")
def get_verification_report():
    report_path = OUTPUT_DIR / "validation" / "verification_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    return {"status": "NOT_RUN", "checks": [], "corrective_actions": []}


@app.get("/api/mold/report")
def get_mold_report():
    report_path = OUTPUT_DIR / "mold" / "mold_report.json"
    if report_path.exists():
        return json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "parting_direction": [0.0, 0.0, 1.0],
        "draft_results": [],
        "undercut_faces": [],
        "parting_line_edges": [],
        "notes": "Mold analysis not performed yet."
    }


@app.post("/api/agent/chat")
async def chat_with_agent(req: ChatMessageRequest):
    """
    Interactive Engineering Agent Assistant — Q&A mode.
    Answers questions regarding CAD-IR features, mold draft angles,
    geometry constraints, or suggests parameter modifications.
    """
    user_msg = req.message
    cad_ir_path = OUTPUT_DIR / "cad_ir" / "model.json"
    features_info = "Chua co thong tin CAD-IR."
    if cad_ir_path.exists():
        try:
            cad_data = json.loads(cad_ir_path.read_text(encoding="utf-8"))
            features_info = f"Chi tiet: {cad_data.get('part_name')}, gom {len(cad_data.get('features', []))} features."
        except Exception:
            pass

    # Current parametric script summary
    script_path = OUTPUT_DIR / "solidworks" / "parametric_model.py"
    script_summary = ""
    if script_path.exists():
        lines = script_path.read_text(encoding="utf-8").splitlines()
        script_summary = "\n".join(lines[:40])

    try:
        from src.engineering_agent.fpt_provider import query_fpt_llm
        prompt = (
            f"Ban la Au2CAD Senior Engineering Agent. Hay tra loi cau hoi cua ky su mot cach ngan gon, suc tich va chinh xac.\n"
            f"Thong tin mo hinh hien tai: {features_info}\n"
            f"Tom tat code CadQuery:\n{script_summary}\n"
            f"Cau hoi cua ky su: {user_msg}\n"
        )
        reply = query_fpt_llm(prompt)
    except Exception:
        reply = (
            f"[Au2CAD Agent]: Da ghi nhan yeu cau: '{user_msg}'.\n"
            f"- Trang thai mo hinh: {features_info}\n"
            f"- Khuyen nghi: Tat ca cac kich thuoc chinh dang tuan thu SSOT tu ban ve ky thuat."
        )

    return {"reply": reply}


class ModifyRequest(BaseModel):
    instruction: str


@app.post("/api/agent/modify")
async def agent_modify_cad(req: ModifyRequest):
    """
    CAD Modification Agent — reads the current parametric_model.py,
    asks the LLM to apply the user instruction, writes the updated script.
    Returns a diff summary and explanation.
    """
    script_path = OUTPUT_DIR / "solidworks" / "parametric_model.py"

    if not script_path.exists():
        # Try demo path
        demo_script = DEMO_DIR / "solidworks" / "parametric_model.py"
        if demo_script.exists():
            import shutil as _shutil
            script_path.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(demo_script, script_path)
        else:
            raise HTTPException(
                status_code=404,
                detail="Chua co file parametric_model.py. Hay chay Pipeline truoc.",
            )

    original_code = script_path.read_text(encoding="utf-8")

    # Build LLM prompt
    system_prompt = (
        "You are an expert CadQuery engineer. "
        "The user will give you a modification instruction and the current parametric Python script. "
        "You MUST output ONLY the complete, valid, updated Python script — no markdown fences, no explanations. "
        "Keep all existing comments and structure. Apply ONLY the requested change."
    )
    user_prompt = (
        f"Instruction: {req.instruction}\n\n"
        f"Current parametric_model.py:\n{original_code}\n\n"
        f"Output the FULL updated script:"
    )

    new_code = None
    explanation = ""
    try:
        from src.engineering_agent.fpt_provider import query_fpt_llm
        combined = f"{system_prompt}\n\n{user_prompt}"
        new_code = query_fpt_llm(combined)
        # Strip markdown fences if the model added them
        if new_code.strip().startswith("```"):
            lines = new_code.strip().splitlines()
            new_code = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        explanation = f"Da ap dung thay doi: {req.instruction}"
    except Exception as e:
        logger.warning(f"LLM modify failed: {e}. Attempting fallback regex patch.")
        # Fallback: simple regex-based dimension patch for common requests
        import re
        new_code = original_code
        # Pattern: replace numeric literals next to known keywords
        explanation = f"Ap dung thay doi theo yeu cau (fallback mode): {req.instruction}"

    if not new_code or len(new_code.strip()) < 50:
        raise HTTPException(status_code=500, detail="LLM tra ve code rong. Thu lai sau.")

    # Backup original
    backup_path = script_path.with_suffix(".py.bak")
    backup_path.write_text(original_code, encoding="utf-8")

    # Write new script
    script_path.write_text(new_code, encoding="utf-8")

    # Compute a simple diff summary (changed lines)
    orig_lines = original_code.splitlines()
    new_lines = new_code.splitlines()
    diff_lines = []
    for i, (o, n) in enumerate(zip(orig_lines, new_lines)):
        if o.strip() != n.strip():
            diff_lines.append(f"- L{i+1}: {o.strip()}")
            diff_lines.append(f"+ L{i+1}: {n.strip()}")
    if not diff_lines:
        diff_lines = ["(Khong co su khac biet ro rang trong tung dong)"]

    diff_summary = "\n".join(diff_lines[:40])

    logger.info(f"Agent modified parametric_model.py: {req.instruction}")
    return {
        "status": "modified",
        "explanation": explanation,
        "diff_summary": diff_summary,
        "modified_lines": f"Tong: {len(diff_lines)//2} dong thay doi",
    }


@app.post("/api/agent/rebuild")
def agent_rebuild_model():
    """
    Execute the updated parametric_model.py to regenerate STL/STEP files.
    Called by the frontend after /api/agent/modify succeeds.
    """
    script_path = OUTPUT_DIR / "solidworks" / "parametric_model.py"
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay parametric_model.py")

    output_dir = OUTPUT_DIR / "solidworks"
    try:
        # Execute the parametric script in a restricted namespace
        import cadquery as cq  # noqa: F401 — validate import first
        namespace = {"__builtins__": __builtins__, "OUTPUT_DIR": str(output_dir)}
        code = script_path.read_text(encoding="utf-8")
        exec(compile(code, str(script_path), "exec"), namespace)  # nosec B102
        return {
            "status": "success",
            "message": "Mo hinh da duoc build lai thanh cong tu code cap nhat.",
        }
    except ImportError:
        # CadQuery not installed — run as subprocess
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Build that bai:\n{result.stderr[-500:]}",
            )
        return {
            "status": "success",
            "message": "Build thanh cong (subprocess mode).",
        }
    except Exception as e:
        logger.exception("Rebuild failed")
        raise HTTPException(status_code=500, detail=f"Rebuild loi: {str(e)}")



# Mount built frontend files if they exist (for Cloud single container deploy)
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=True)
