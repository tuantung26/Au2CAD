"""
CadQuery Adapter
=================
Translates a CADIR object into a runnable CadQuery script,
executes it, and exports the result as .STEP (and optionally .STL).

This adapter plays the role of the "SolidWorks Adapter" in the
architecture, but uses the open-source CadQuery/OpenCascade stack
so the demo runs without a SolidWorks licence.

When SolidWorks integration is added later, a SolidWorksAdapter
can be dropped in implementing the same interface (AdapterBase).

Public API
----------
    adapter = CadQueryAdapter()
    result = adapter.build(cadir, output_dir=Path("demo_part/solidworks"))
    # result.step_path  → .step file
    # result.success    → bool
"""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from src.models import CADIR, CADFeature, FeatureType

logger = logging.getLogger(__name__)


# ── Result ────────────────────────────────────────────────────

@dataclass
class AdapterResult:
    success: bool
    step_path: Path | None = None
    stl_path: Path | None = None
    script_path: Path | None = None
    error: str = ""
    log: list[str] = field(default_factory=list)


# ── Adapter ───────────────────────────────────────────────────

class CadQueryAdapter:
    """
    Converts CADIR → CadQuery Python script → executes → exports STEP.

    Strategy:
    * Code-generate a CadQuery script from the feature list.
    * Execute it in-process via exec() in an isolated namespace.
    * Export the resulting solid to STEP.
    * Any feature the adapter cannot translate is logged as a warning.
    """

    def build(self, cadir: CADIR, output_dir: Path) -> AdapterResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        script = self._generate_script(cadir)
        script_path = output_dir / "generated_model.py"
        script_path.write_text(script, encoding="utf-8")

        step_path = output_dir / "generated.STEP"
        stl_path = output_dir / "generated.stl"

        result = self._execute_script(script, step_path, stl_path)
        result.script_path = script_path
        return result

    # ── Code generation ───────────────────────────────────────

    def _generate_script(self, cadir: CADIR) -> str:
        lines: list[str] = [
            "import cadquery as cq",
            "",
            f"# Auto-generated from CAD-IR — part: {cadir.part_name}",
            "# Units: " + cadir.units,
            "",
            "result = None",
        ]

        is_first = True
        for feat in cadir.features:
            snippet = self._feature_to_cq(feat, is_first=is_first)
            if snippet:
                if is_first:
                    # First feature must succeed to define base solid
                    lines.append(snippet)
                    is_first = False
                elif feat.type in (FeatureType.FILLET, FeatureType.CHAMFER):
                    lines.append(f"try:\n    {snippet}\nexcept Exception as _e:\n    pass  # Delicate edge blend skipped")
                else:
                    lines.append(f"try:\n    {snippet}\nexcept Exception as _e:\n    print(f'Warning: Feature {feat.id} error: {{_e}}')")
            else:
                lines.append(f"# [SKIPPED] Unsupported feature: {feat.id} ({feat.type})")
                logger.warning("Skipping unsupported feature: %s (%s)", feat.id, feat.type)

        return "\n".join(lines) + "\n"

    def _feature_to_cq(self, feat: CADFeature, is_first: bool = False) -> str | None:
        """Return a CadQuery method call string for the feature."""
        params = {p.name: p.value for p in feat.parameters}

        def _to_float(val, default):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        wp = feat.workplane or "XY"
        cx = feat.center[0] if (feat.center and len(feat.center) > 0) else _to_float(params.get("x", params.get("center_x")), 0)
        cy = feat.center[1] if (feat.center and len(feat.center) > 1) else _to_float(params.get("y", params.get("center_y")), 0)

        # ── EXTRUDE (Boxes, Plates, Bosses, Cylinders) ──
        if feat.type == FeatureType.EXTRUDE:
            is_cylinder = (
                feat.profile in ("circle", "cylinder", "cylindrical")
                or feat.diameter is not None
                or "diameter" in params
                or "radius" in params
            )

            if is_cylinder:
                diam = _to_float(feat.diameter or params.get("diameter"), None)
                if diam is None:
                    rad = _to_float(feat.radius or params.get("radius"), 25)
                    diam = rad * 2
                r = diam / 2
                h = _to_float(feat.depth or params.get("height", params.get("depth")), 20)

                if is_first:
                    return f"result = cq.Workplane('{wp}').moveTo({cx}, {cy}).circle({r}).extrude({h})"
                else:
                    if feat.operation == "cut":
                        if feat.through_all:
                            return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).circle({r}).cutThruAll()"
                        else:
                            return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).circle({r}).cutBlind(-{h})"
                    else:
                        return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).circle({r}).extrude({h})"

            else:
                l = _to_float(params.get("length"), 100)
                w = _to_float(params.get("width"), 60)
                h = _to_float(feat.depth or params.get("height", params.get("depth")), 10)

                if is_first:
                    if cx == 0 and cy == 0:
                        return f"result = cq.Workplane('{wp}').box({l}, {w}, {h})"
                    else:
                        return f"result = cq.Workplane('{wp}').moveTo({cx}, {cy}).rect({l}, {w}).extrude({h})"
                else:
                    if feat.operation == "cut":
                        if feat.through_all:
                            return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).rect({l}, {w}).cutThruAll()"
                        else:
                            return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).rect({l}, {w}).cutBlind(-{h})"
                    else:
                        return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).rect({l}, {w}).extrude({h})"

        # ── HOLE & PATTERN ──
        elif feat.type in (FeatureType.HOLE, FeatureType.PATTERN):
            pcd = _to_float(feat.bolt_circle_diameter or params.get("bolt_circle_diameter", params.get("pcd")), None)
            hole_cnt = feat.hole_count or int(_to_float(params.get("hole_count", params.get("count")), 0))

            if pcd is not None and hole_cnt > 1:
                diam = _to_float(feat.diameter or params.get("diameter"), 10)
                depth = _to_float(feat.depth or params.get("depth"), None)
                if feat.through_all or depth is None:
                    return f"result = result.faces('>Z').workplane().polarArray({pcd / 2}, 0, 360, {hole_cnt}).hole({diam})"
                else:
                    return f"result = result.faces('>Z').workplane().polarArray({pcd / 2}, 0, 360, {hole_cnt}).hole({diam}, {depth})"

            else:
                diam = _to_float(feat.diameter or params.get("diameter"), 10)
                depth = _to_float(feat.depth or params.get("depth"), None)
                if feat.through_all or depth is None:
                    return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).hole({diam})"
                else:
                    return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).hole({diam}, {depth})"

        # ── CUT (Pockets, Slots, Counterbores) ──
        elif feat.type == FeatureType.CUT:
            depth = _to_float(feat.depth or params.get("depth"), 10)
            is_circle = (
                feat.profile in ("circle", "cylinder")
                or feat.diameter is not None
                or "diameter" in params
                or "radius" in params
            )

            if is_circle:
                diam = _to_float(feat.diameter or params.get("diameter"), 10)
                r = diam / 2
                if feat.through_all:
                    return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).circle({r}).cutThruAll()"
                else:
                    return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).circle({r}).cutBlind(-{depth})"
            else:
                l = _to_float(params.get("length", params.get("width")), 10)
                w = _to_float(params.get("width"), 10)
                if feat.through_all:
                    return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).rect({l}, {w}).cutThruAll()"
                else:
                    return f"result = result.faces('>Z').workplane().moveTo({cx}, {cy}).rect({l}, {w}).cutBlind(-{depth})"

        # ── FILLET & CHAMFER ──
        elif feat.type == FeatureType.FILLET:
            r = _to_float(feat.radius or params.get("radius"), 1)
            return f"result = result.edges('|Z').fillet({r})"

        elif feat.type == FeatureType.CHAMFER:
            r = _to_float(feat.radius or params.get("radius"), 1)
            return f"result = result.edges('|Z').chamfer({r})"

        # ── SWEEP & PIPE (Curved cylinders, bent pipes, U-tubes) ──
        elif feat.type in (FeatureType.SWEEP, FeatureType.PIPE):
            diam = _to_float(feat.diameter or params.get("diameter", params.get("outer_diameter")), 20)
            r_out = diam / 2
            inner_diam = _to_float(getattr(feat, "inner_diameter", None) or params.get("inner_diameter"), None)
            r_in = (inner_diam / 2) if inner_diam else None

            path_plane = getattr(feat, "path_plane", "XZ") or "XZ"
            prof_plane = feat.workplane or "XY"
            path_pts = getattr(feat, "path_points", None) or params.get("path_points")
            path_type = getattr(feat, "path_type", "spline") or params.get("path_type", "spline")

            # Default U-bend trajectory if none specified or if path_type is u_bend
            if path_type in ("u_bend", "u_tube") or not path_pts:
                span_w = _to_float(params.get("width", params.get("span")), 50)
                height = _to_float(feat.depth or params.get("height", params.get("length")), 60)
                path_pts = [
                    [0.0, 0.0],
                    [0.0, height * 0.6],
                    [span_w * 0.5, height],
                    [span_w, height * 0.6],
                    [span_w, 0.0],
                ]

            pts_repr = repr([[float(p[0]), float(p[1])] for p in path_pts])

            # Construct sweep solid code
            if r_in:
                pipe_gen = f"cq.Workplane('{prof_plane}').circle({r_out}).circle({r_in}).sweep(cq.Workplane('{path_plane}').spline({pts_repr}))"
            else:
                pipe_gen = f"cq.Workplane('{prof_plane}').circle({r_out}).sweep(cq.Workplane('{path_plane}').spline({pts_repr}))"

            if is_first:
                return f"result = {pipe_gen}"
            else:
                if feat.operation == "cut":
                    return f"result = result.cut({pipe_gen})"
                else:
                    return f"result = result.union({pipe_gen})"

        # ── REVOLVE ──
        elif feat.type == FeatureType.REVOLVE:
            angle = _to_float(feat.angle or params.get("angle"), 360)
            return f"result = result.revolve({angle})"

        return None  # unsupported

    # ── Execution ─────────────────────────────────────────────

    def _execute_script(self, script: str, step_path: Path, stl_path: Path) -> AdapterResult:
        logs: list[str] = []
        try:
            import cadquery as cq

            namespace: dict = {}
            exec(compile(script, "<cadir_generated>", "exec"), namespace)  # noqa: S102

            solid = namespace.get("result")
            if solid is None:
                return AdapterResult(success=False, error="Script executed but 'result' is None.")

            # Export STEP
            cq.exporters.export(solid, str(step_path))
            logs.append(f"STEP exported → {step_path}")

            # Export STL
            cq.exporters.export(solid, str(stl_path))
            logs.append(f"STL exported → {stl_path}")

            logger.info("CadQueryAdapter build successful.")
            return AdapterResult(
                success=True,
                step_path=step_path,
                stl_path=stl_path,
                log=logs,
            )

        except ImportError:
            return AdapterResult(
                success=False,
                error="CadQuery not installed. Run: pip install cadquery",
            )
        except Exception as exc:
            logger.exception("CadQueryAdapter execution failed")
            return AdapterResult(success=False, error=str(exc), log=logs)
