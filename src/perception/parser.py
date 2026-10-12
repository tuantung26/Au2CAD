"""
Module 1: Perception / Parser Implementation
============================================
Parses 2D blueprint descriptions, dimensions, centerlines, and view mappings
into structured raw features and candidate constraints.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.engineering_agent.agent import invoke_llm_with_fallback
from src.perception.models import CandidateConstraint, PerceptionOutput, RawFeature

logger = logging.getLogger(__name__)

PERCEPTION_PROMPT_TEMPLATE = """You are a Principal Mechanical CAD Perception Engine.
CORE RULE: The [BLUEPRINT VLM NOTES] is the PRIMARY SINGLE SOURCE OF TRUTH (SSOT).
Any [ENGINEER CONTEXT / SPECIFICATION] is strictly secondary and auxiliary. If the context contains irrelevant text (such as web browser tabs, system metadata, or contradictory notes), IGNORE IT COMPLETELY and reconstruct the CAD model 100% from the blueprint drawing.

Your mission is to extract:
1. An EXHAUSTIVE inventory of all 3D primitive shapes and their exact quantities (no missing blocks, no missing holes).
2. The ASSEMBLY & JOINING TOPOLOGY: How each shape attaches to its parent body (which face, what operation: ADD/SUBTRACT/BLEND, and relative position).
3. Geometric constraints (coaxial, symmetric, concentric, tangent).

Input Engineering Data:
-----------------------
[BLUEPRINT VLM NOTES (PRIMARY SINGLE SOURCE OF TRUTH)]
{drawing_notes}

[AUXILIARY CONTEXT / NOTES (OPTIONAL - SECONDARY ONLY)]
{context}

Respond STRICTLY with a single valid JSON object adhering to this schema:
{{
  "part_name": "PartName",
  "overview": "Clear summary of the mechanical component based on the blueprint",
  "drawing_is_primary_truth": true,
  "centerlines": ["axis_longitudinal_centerline"],
  "raw_features": [
    {{
      "id": "F1_BaseBlock",
      "feature_type": "box",
      "description": "Primary base mounting solid",
      "quantity": 1,
      "dimensions": {{"length": 100.0, "width": 62.0, "height": 18.0}},
      "parent_feature": null,
      "attachment_face": "root",
      "join_operation": "ADD",
      "relative_offset": [0.0, 0.0, 0.0],
      "view_source": "top_view",
      "primary_source": "drawing"
    }},
    {{
      "id": "F2_UpperBoss",
      "feature_type": "cylinder",
      "description": "Upper cylindrical bearing housing",
      "quantity": 1,
      "dimensions": {{"diameter": 44.0, "length": 40.0}},
      "parent_feature": "F1_BaseBlock",
      "attachment_face": "top",
      "join_operation": "ADD",
      "relative_offset": [0.0, 0.0, 32.0],
      "view_source": "front_view",
      "primary_source": "drawing"
    }},
    {{
      "id": "F3_CentralBore",
      "feature_type": "bore",
      "description": "Through-bore in upper boss",
      "quantity": 1,
      "dimensions": {{"diameter": 28.0}},
      "parent_feature": "F2_UpperBoss",
      "attachment_face": "coaxial",
      "join_operation": "SUBTRACT",
      "relative_offset": [0.0, 0.0, 0.0],
      "view_source": "section_A-A",
      "primary_source": "drawing"
    }},
    {{
      "id": "F4_BottomSlot",
      "feature_type": "notch",
      "description": "Underside rectangular recess slot",
      "quantity": 1,
      "dimensions": {{"width": 28.0, "height": 9.0, "depth": 100.0}},
      "parent_feature": "F1_BaseBlock",
      "attachment_face": "bottom",
      "join_operation": "SUBTRACT",
      "relative_offset": [0.0, -8.0, 0.0],
      "view_source": "side_view",
      "primary_source": "drawing"
    }}
  ],
  "candidate_constraints": [
    {{
      "type": "coaxial",
      "features": ["F2_UpperBoss", "F3_CentralBore"],
      "datum": "axis_boss_centerline",
      "note": "Shared center axis"
    }}
  ],
  "assembly_join_sequence": [
    "F1_BaseBlock is root solid on XY plane",
    "F2_UpperBoss attaches to top face of F1_BaseBlock with ADD",
    "F3_CentralBore cuts coaxially through F2_UpperBoss with SUBTRACT",
    "F4_BottomSlot cuts underside of F1_BaseBlock with SUBTRACT"
  ]
}}
"""


class DrawingPerceptionParser:
    """Parses drawing and engineer text into structured PerceptionOutput."""

    def parse(self, drawing_notes: str = "", context: str = "") -> PerceptionOutput:
        """Execute perception parsing to extract raw features and candidate constraints."""
        logger.info("[Perception/Parser] Decomposing drawing and specification into raw features & constraints...")

        prompt = PERCEPTION_PROMPT_TEMPLATE.format(
            drawing_notes=drawing_notes.strip() or "None",
            context=context.strip() or "None",
        )

        try:
            raw_response = invoke_llm_with_fallback(prompt)
            data = self._extract_json(raw_response)
            if data:
                output = PerceptionOutput(**data)
                logger.info(
                    "[Perception/Parser] Successfully extracted %d raw features, %d constraints, %d centerlines.",
                    len(output.raw_features),
                    len(output.candidate_constraints),
                    len(output.centerlines),
                )
                return output
            logger.warning("[Perception/Parser] Failed to extract valid JSON; returning fallback output.")
        except Exception as exc:
            logger.error("[Perception/Parser] Parsing error: %s", exc)

        return self._build_fallback(context)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Extract JSON dictionary from text with markdown fence handling."""
        text = text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return None

    def _build_fallback(self, context: str) -> PerceptionOutput:
        """Deterministic baseline fallback if LLM is unavailable."""
        return PerceptionOutput(
            part_name="SteppedShaftDefault",
            overview="Baseline stepped shaft extracted from default parameters",
            centerlines=["axis_main"],
            raw_features=[
                RawFeature(
                    id="F1_Head",
                    feature_type="box",
                    dimensions={"length": 50.0, "width": 25.0, "height": 42.0},
                    operation="add",
                ),
                RawFeature(
                    id="F2_Body",
                    feature_type="cylinder",
                    dimensions={"diameter": 60.0, "length": 45.0},
                    axis_or_centerline="axis_main",
                    operation="add",
                ),
                RawFeature(
                    id="F3_Bore",
                    feature_type="bore",
                    dimensions={"diameter": 25.0},
                    axis_or_centerline="axis_main",
                    operation="cut",
                ),
            ],
            candidate_constraints=[
                CandidateConstraint(
                    type="coaxial",
                    features=["F2_Body", "F3_Bore"],
                    datum="axis_main",
                    note="Coaxial alignment along main axis",
                )
            ],
        )
