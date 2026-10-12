"""
CADFit Program → CAD-IR Parser
================================
Reads the CadQuery script that CADFit outputs and converts it into
the structured CAD-IR (src/models.py → CADIR) so the Engineering Agent
can reason over it without parsing Python code.

Strategy
--------
* We use a lightweight AST-based approach to extract high-level
  CadQuery method calls (box, circle, extrude, fillet, chamfer …).
* We do NOT execute the script — parsing only.
* Each recognised call becomes a CADFeature in the CADIR.
* Unknown/complex calls are stored as metadata for the Agent to handle.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from src.models import CADIR, CADFeature, FeatureType, Parameter

logger = logging.getLogger(__name__)

# Mapping from CadQuery method name → FeatureType
_CADQUERY_METHOD_MAP: dict[str, FeatureType] = {
    "box": FeatureType.EXTRUDE,
    "extrude": FeatureType.EXTRUDE,
    "cylinder": FeatureType.REVOLVE,
    "revolve": FeatureType.REVOLVE,
    "cut": FeatureType.CUT,
    "cutThruAll": FeatureType.CUT,
    "cutBlind": FeatureType.CUT,
    "union": FeatureType.UNION,
    "add": FeatureType.UNION,
    "fillet": FeatureType.FILLET,
    "chamfer": FeatureType.CHAMFER,
    "hole": FeatureType.HOLE,
    "cboreHole": FeatureType.HOLE,
    "cskHole": FeatureType.HOLE,
    "shell": FeatureType.SHELL,
}


class CADFitProgramParser:
    """
    Parses a CADFit-generated CadQuery program into a CADIR object.
    """

    def __init__(self, part_name: str = "part") -> None:
        self.part_name = part_name

    def parse_file(self, program_path: Path) -> CADIR:
        source = program_path.read_text(encoding="utf-8")
        return self.parse_source(source)

    def parse_source(self, source: str) -> CADIR:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.error("Failed to parse CADFit program: %s", exc)
            return CADIR(part_name=self.part_name, metadata={"parse_error": str(exc)})

        features: list[CADFeature] = []
        visitor = _MethodCallVisitor()
        visitor.visit(tree)

        for idx, call in enumerate(visitor.calls):
            feature = self._call_to_feature(f"F{idx + 1}", call)
            if feature:
                features.append(feature)

        ir = CADIR(
            part_name=self.part_name,
            features=features,
            metadata={"source_calls": len(visitor.calls), "recognised": len(features)},
        )
        logger.info(
            "Parsed CADFit program → %d features recognised from %d calls",
            len(features),
            len(visitor.calls),
        )
        return ir

    # ── Helpers ───────────────────────────────────────────────

    def _call_to_feature(self, fid: str, call: dict) -> CADFeature | None:
        method = call["method"]
        feat_type = _CADQUERY_METHOD_MAP.get(method)
        if feat_type is None:
            return None

        args = call.get("args", [])
        kwargs = call.get("kwargs", {})

        feature = CADFeature(id=fid, type=feat_type, metadata={"cq_method": method})

        # --- EXTRUDE / box ---
        if method == "box" and len(args) >= 3:
            feature.parameters = [
                Parameter(name="length", value=float(args[0])),
                Parameter(name="width", value=float(args[1])),
                Parameter(name="height", value=float(args[2])),
            ]
            feature.depth = float(args[2])

        elif method in ("extrude", "cutBlind") and args:
            feature.depth = float(args[0])
            feature.parameters = [Parameter(name="depth", value=float(args[0]))]

        # --- FILLET / CHAMFER ---
        elif method in ("fillet", "chamfer") and args:
            feature.radius = float(args[0])
            feature.parameters = [Parameter(name="radius", value=float(args[0]))]

        # --- HOLE ---
        elif method in ("hole", "cboreHole", "cskHole"):
            diameter = kwargs.get("diameter") or (args[0] if args else None)
            if diameter is not None:
                feature.diameter = float(diameter)
                feature.parameters = [Parameter(name="diameter", value=float(diameter))]
            depth = kwargs.get("depth") or (args[1] if len(args) > 1 else None)
            if depth is not None:
                feature.depth = float(depth)
            else:
                feature.through_all = True

        # --- REVOLVE ---
        elif method in ("revolve", "cylinder"):
            angle = kwargs.get("angleDegrees") or 360.0
            feature.angle = float(angle)

        return feature


# ── AST visitor ───────────────────────────────────────────────

class _MethodCallVisitor(ast.NodeVisitor):
    """
    Walks the AST and collects all method call names + their arguments.
    Only captures literal numeric arguments for safety.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            args = [self._literal(a) for a in node.args]
            kwargs = {
                kw.arg: self._literal(kw.value)
                for kw in node.keywords
                if kw.arg is not None
            }
            self.calls.append({"method": method, "args": args, "kwargs": kwargs})
        self.generic_visit(node)

    @staticmethod
    def _literal(node: ast.expr) -> float | str | None:
        try:
            val = ast.literal_eval(node)
            return val
        except Exception:
            return None
