"""
Au2CAD — Main Pipeline Entry Point
====================================
Runs the full end-to-end pipeline:

  Multi-view images  (Hunyuan3D — skipped for demo, provide mesh directly)
        ↓
  Mesh Preprocessing
        ↓
  CADFit  (real or mock)
        ↓
  CAD-IR
        ↓
  Engineering Agent  (LLM — provider set in .env)
        ↓
  CadQuery Adapter  → .STEP
        ↓
  Geometry Validator
        ↓
  Mold Design Analyst
        ↓
  Engineer Review Report

Usage:
    python src/main.py --input demo_part/reconstruction/raw_mesh.obj
    python src/main.py --input demo_part/reconstruction/raw_mesh.obj --mock-cadfit
    python src/main.py --help
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

app = typer.Typer(help="Au2CAD — Agentic Reverse Engineering Pipeline")
console = Console(highlight=False)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


@app.command()
def run(
    input_drawing: Path = typer.Option(Path("demo_part/input/drawing/technical_drawing.pdf"), "--input-drawing", "-d", help="Technical drawing file (.pdf/.png/.jpg)"),
    input_context: Path = typer.Option(Path("demo_part/input/description.txt"), "--input-context", "-c", help="Text file with engineer description / notes (.txt)"),
    output_dir: Path = typer.Option(Path("output"), "--output", "-o", help="Output directory"),
    skip_agent: bool = typer.Option(False, "--skip-agent", help="Skip LLM agent step"),
    skip_mold: bool = typer.Option(False, "--skip-mold", help="Skip mold design analysis"),
    clean_output: bool = typer.Option(True, "--clean/--no-clean", help="Automatically clean old output files before generating new ones (default: True)"),
):
    """Run the Au2CAD Drawing-led SSOT pipeline from technical drawing to parametric CAD and mold report."""

    # Read context file if provided and exists
    context_text = ""
    if input_context and input_context.exists():
        context_text = input_context.read_text(encoding="utf-8")

    # Auto-detect drawing file if default path does not exist
    if not (input_drawing and input_drawing.exists()):
        drawing_dir = Path("demo_part/input/drawing")
        if drawing_dir.exists():
            for ext in ("*.jpg", "*.png", "*.jpeg", "*.pdf", "*.webp"):
                candidates = sorted(drawing_dir.glob(ext))
                if candidates:
                    input_drawing = candidates[0]
                    break

    has_drawing = input_drawing and input_drawing.exists()

    if not has_drawing and not context_text:
        console.print("[red]Error:[/red] Could not find any input files (drawing or description.txt).")
        raise typer.Exit(1)

    console.print(Panel.fit(
        "[bold cyan]Au2CAD -- Multi-Modal Agentic CAD System (SSOT)[/bold cyan]\n"
        "Blueprint Drawing -> CAD-IR -> Parametric Solid -> Verification -> Mold",
        border_style="cyan",
    ))
    if has_drawing:
        console.print(f"  [cyan]Technical Drawing blueprint detected:[/cyan] {input_drawing.name}")
        console.print("  [bold yellow]* Single Source of Truth (SSOT):[/bold yellow] Blueprint drawing drives 100% of geometry.")
        console.print("  [dim]Auxiliary context/description text is strictly secondary hints.[/dim]\n")

    # Clean old outputs if requested
    if clean_output and output_dir.exists():
        _clean_dir(output_dir)
        console.print(f"  [dim]Cleaned old files in: {output_dir.resolve()}[/dim]\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    dirs = _make_subdirs(output_dir)

    final_step_path = None
    final_cadir = None

    # ── Module 1: Perception / Parser ───────────────────────
    _section("1 / 4  Perception / Parser (Drawing-First SSOT)")
    from src.engineering_agent.vlm_extractor import analyze_drawing
    from src.perception import BlueprintFeatureDimensionExtractor, DrawingPerceptionParser

    drawing_notes = ""
    structured_manifest = None
    if has_drawing:
        console.print(f"  [cyan]Inspecting blueprint drawing (Primary SSOT):[/cyan] {input_drawing.name}")
        drawing_notes = analyze_drawing(input_drawing)

        # Dedicated Structured Dimension & Shape Extractor (Pydantic Schema)
        dim_extractor = BlueprintFeatureDimensionExtractor()
        structured_manifest = dim_extractor.extract(input_drawing)
        manifest_path = output_dir / "structured_dimensions.json"
        manifest_path.write_text(structured_manifest.model_dump_json(indent=2), encoding="utf-8")
        console.print("  [bold green]Structured Output Extracted (Pydantic Schema):[/bold green]")
        console.print(f"    • Base Plate:     [cyan]{structured_manifest.base_plate.length_mm} x {structured_manifest.base_plate.width_mm} x {structured_manifest.base_plate.thickness_mm} mm[/cyan]")
        console.print(f"    • Upper Boss:     [cyan]OD={structured_manifest.upper_boss.outer_diameter_mm} mm, ID={structured_manifest.upper_boss.inner_bore_diameter_mm} mm, Center Z={structured_manifest.upper_boss.center_height_from_base_mm} mm[/cyan]")
        console.print(f"    • Bottom Slot:    [cyan]{structured_manifest.bottom_slot.width_mm} x {structured_manifest.bottom_slot.height_mm} mm (offset {structured_manifest.bottom_slot.offset_from_reference_face_mm} mm)[/cyan]")
        console.print(f"    • Front Cutout:   [cyan]R{structured_manifest.front_cutout.radius_mm} mm[/cyan]")
        console.print(f"    • Transition Web: [cyan]Thickness={structured_manifest.transition_web.thickness_mm} mm[/cyan]")
        console.print(f"    • Dimension Table: [green]{len(structured_manifest.dimension_constants)} ground truth constants locked[/green]")

    parser = DrawingPerceptionParser()
    perception_output = parser.parse(drawing_notes=drawing_notes, context=context_text)
    perception_path = output_dir / "perception.json"
    perception_path.write_text(perception_output.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"  Raw features parsed:    [green]{len(perception_output.raw_features)}[/green]")
    console.print(f"  Candidate constraints:  [green]{len(perception_output.candidate_constraints)}[/green]")
    console.print(f"  Perception summary:     [dim]{perception_output.overview}[/dim]")
    if perception_output.assembly_join_sequence:
        console.print("  [bold cyan]Assembly / Join Topology:[/bold cyan]")
        for step in perception_output.assembly_join_sequence:
            console.print(f"    ↳ {step}")

    # ── Module 2: Geometry Graph Builder ────────────────────
    _section("2 / 4  Geometry Graph Builder")
    from src.geometry_graph import GeometryGraphBuilder

    graph_builder = GeometryGraphBuilder()
    graph = graph_builder.build_graph(perception_output)
    final_cadir = graph_builder.resolve_to_cadir(perception_output)
    cadir_path = dirs["cad_ir"] / "model.json"
    final_cadir.to_json(cadir_path)

    console.print(f"  Constraint Graph nodes: [green]{graph.number_of_nodes()}[/green]")
    console.print(f"  Constraint Graph edges: [green]{graph.number_of_edges()}[/green]")
    if graph_builder.report.conflicts:
        for conf in graph_builder.report.conflicts:
            console.print(f"  [red]Conflict detected:[/red] {conf}")
    else:
        console.print("  Dimensional conflicts:  [green]0 (Consistent)[/green]")
    console.print(f"  Resolved CAD-IR saved:  [cyan]{cadir_path}[/cyan]")

    # ── Module 3: Parametric Builder ────────────────────────
    _section("3 / 4  Parametric Builder (Multimodal: Drawing + Structured Dimensions + Prompt)")
    from src.parametric_builder import ParametricCadQueryBuilder

    console.print("  [bold cyan]Inputs to Code Generator:[/bold cyan]")
    console.print(f"    • Technical Drawing (Image):    [green]{input_drawing.name if has_drawing else 'None'}[/green]")
    console.print(f"    • Structured Dimensions (SSOT): [green]Locked via Pydantic ({len(structured_manifest.dimension_constants) if structured_manifest else 0} constants)[/green]")
    console.print(f"    • Blueprint Perception (Notes):   [green]{len(drawing_notes)} characters[/green]")
    console.print("    • CadQuery Prompt & Enforcer:   [green]Ground Truth Constants Enforced (No Hallucination)[/green]")
    console.print("    • SSOT Priority:                [bold yellow]Drawing is Primary Single Source of Truth[/bold yellow]")

    builder = ParametricCadQueryBuilder()
    build_result = builder.build(
        cadir=final_cadir,
        output_dir=dirs["solidworks"],
        input_drawing=input_drawing if has_drawing else None,
        drawing_notes=drawing_notes,
        feature_manifest=structured_manifest,
        auxiliary_context=context_text,
    )

    if build_result.success:
        final_step_path = build_result.step_path
        console.print(f"  STEP solid model:       [cyan]{build_result.step_path}[/cyan]")
        console.print(f"  STL mesh model:         [cyan]{build_result.stl_path}[/cyan]")
        console.print(f"  Parametric script:      [cyan]{build_result.script_path}[/cyan]")
    else:
        console.print(f"  [red]Build failed:[/red] {build_result.error}")
        raise typer.Exit(1)

    # ── Module 4: Verifier (Symbolic & Geometric) ───────────
    _section("4 / 4  Verifier (Symbolic & Geometric)")
    from src.verifier import SymbolicCADVerifier

    verifier = SymbolicCADVerifier()
    verification_report = verifier.verify(
        cq_model=build_result.cq_model,
        cadir=final_cadir,
        perception=perception_output,
    )

    from dataclasses import asdict
    v_path = dirs["validation"] / "verification_report.json"
    v_path.write_text(json.dumps(asdict(verification_report), indent=2), encoding="utf-8")

    status_color = "green" if verification_report.passed else "red"
    console.print(f"  Verification Status:    [{status_color}]{'PASS' if verification_report.passed else 'FAIL'}[/{status_color}]")
    for check in verification_report.checks:
        tag_color = "green" if check.passed else "red"
        console.print(f"    • [{tag_color}]{'OK' if check.passed else 'FAIL'}[/{tag_color}] {check.name}: {check.details}")

    if verification_report.corrective_actions:
        console.print("  [yellow]Corrective Actions / Human Review:[/yellow]")
        for act in verification_report.corrective_actions:
            console.print(f"    - {act}")

    # ── Step 6: Mold Design ─────────────────────────────────────
    _section("5 / 6  Preliminary Mold Design")
    if skip_mold or final_step_path is None:
        console.print("  [yellow]Skipped[/yellow]")
    else:
        stl_path = dirs["solidworks"] / "generated.stl"
        if stl_path.exists():
            from src.mold_design.analyst import MoldAnalyst
            analyst = MoldAnalyst()
            mold_result = analyst.analyse(stl_path, dirs["mold"])
            r = mold_result.report
            console.print(f"  Parting dir:    {r.parting_direction}")
            console.print(f"  Undercuts:      {len(r.undercut_faces)}")
            console.print(f"  Parting edges:  {len(r.parting_line_edges)}")
            console.print(f"  Report ->       [cyan]{mold_result.json_report_path}[/cyan]")
        else:
            console.print("  [yellow]STL not found; skipping mold analysis.[/yellow]")

    # ── Summary ─────────────────────────────────────────────────
    _section("6 / 6  Done")
    console.print(Panel.fit(
        f"[bold green]Pipeline complete[/bold green]\n"
        f"Output directory: {output_dir.resolve()}",
        border_style="green",
    ))


# ── Helpers ───────────────────────────────────────────────────

def _clean_dir(path: Path) -> None:
    """Recursively delete all contents inside path while preserving the directory itself."""
    if not path.exists():
        return
    for item in path.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            logging.getLogger(__name__).warning("Could not delete %s: %s", item, e)


def _make_subdirs(base: Path) -> dict[str, Path]:
    names = ["reconstruction", "cadfit", "cad_ir", "solidworks", "validation", "mold"]
    dirs = {n: base / n for n in names}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _section(title: str) -> None:
    console.print(f"\n[bold white]── {title}[/bold white]")


def _print_stats(title: str, stats: dict) -> None:
    table = Table(title=title, show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)


if __name__ == "__main__":
    app()
