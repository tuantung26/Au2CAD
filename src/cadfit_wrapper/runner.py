"""
CADFit Subprocess Wrapper
==========================
Calls the CADFit executable/script as an external process.
CADFit is treated as a black-box geometry engine:

    Clean Mesh (.obj/.stl)
          ↓
      CADFit
          ↓
    CAD program (CadQuery Python script)
    + result geometry (.step)

Design decisions
----------------
* We do NOT monkey-patch CADFit internals.
* We communicate via filesystem: input mesh → output dir.
* The wrapper parses CADFit stdout for progress / metrics.
* A MockRunner is provided so the rest of the pipeline can be
  developed & tested without a CADFit installation.

Usage:
    from src.cadfit_wrapper import CADFitRunner

    runner = CADFitRunner(cadfit_root=Path("./third_party/CADFit"))
    result = runner.run(
        mesh_path=Path("demo_part/reconstruction/clean_mesh.obj"),
        output_dir=Path("demo_part/cadfit"),
    )
    print(result.iou, result.program_path, result.step_path)
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────

@dataclass
class CADFitResult:
    """Everything CADFit produces for one part."""
    success: bool
    iou: float | None = None
    runtime_s: float | None = None
    program_path: Path | None = None      # .py CadQuery script
    step_path: Path | None = None         # .step geometry
    log: str = ""
    error: str = ""
    metadata: dict = field(default_factory=dict)


# ── Main runner ───────────────────────────────────────────────

class CADFitRunner:
    """
    Wraps CADFit as a subprocess.

    Expected CADFit CLI interface (adjust to actual repo):
        python run_cadfit.py \
            --input  <mesh.obj> \
            --output <output_dir> \
            --max-iter <N>

    CADFit is expected to write:
        <output_dir>/program.py     ← CadQuery reconstruction script
        <output_dir>/result.step    ← exported geometry
        <output_dir>/metrics.json   ← {"iou": 0.91, "runtime_s": 456}
    """

    PROGRAM_FILENAME = "program.py"
    STEP_FILENAME = "result.step"
    METRICS_FILENAME = "metrics.json"

    def __init__(
        self,
        cadfit_root: Path,
        max_iterations: int = 10,
        timeout_s: int = 3600,
        python_executable: str = "python",
    ) -> None:
        self.cadfit_root = Path(cadfit_root).resolve()
        self.max_iterations = max_iterations
        self.timeout_s = timeout_s
        self.python_executable = python_executable

    def run(self, mesh_path: Path, output_dir: Path) -> CADFitResult:
        """
        Execute CADFit on *mesh_path*, write outputs to *output_dir*.
        Returns a CADFitResult regardless of success/failure.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        entry_script = self.cadfit_root / "run_cadfit.py"

        if not self.cadfit_root.exists():
            return CADFitResult(
                success=False,
                error=f"CADFit root not found: {self.cadfit_root}. "
                      "Clone the repo into third_party/CADFit.",
            )

        cmd = [
            self.python_executable,
            str(entry_script),
            "--input", str(mesh_path.resolve()),
            "--output", str(output_dir.resolve()),
            "--max-iter", str(self.max_iterations),
        ]

        logger.info("Running CADFit: %s", " ".join(cmd))
        t0 = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                cwd=str(self.cadfit_root),
            )
            elapsed = time.time() - t0
            log_output = proc.stdout + proc.stderr

            if proc.returncode != 0:
                logger.error("CADFit exited with code %d", proc.returncode)
                return CADFitResult(success=False, runtime_s=elapsed, log=log_output,
                                    error=f"Non-zero exit code: {proc.returncode}")

            return self._parse_output(output_dir, elapsed, log_output)

        except subprocess.TimeoutExpired:
            return CADFitResult(success=False, error=f"Timeout after {self.timeout_s}s")
        except Exception as exc:
            return CADFitResult(success=False, error=str(exc))

    # ── Internal helpers ──────────────────────────────────────

    def _parse_output(self, output_dir: Path, elapsed: float, log: str) -> CADFitResult:
        program = output_dir / self.PROGRAM_FILENAME
        step = output_dir / self.STEP_FILENAME
        metrics_file = output_dir / self.METRICS_FILENAME

        iou: float | None = None
        metadata: dict = {}

        if metrics_file.exists():
            with metrics_file.open() as f:
                metrics = json.load(f)
            iou = metrics.get("iou")
            metadata = metrics

        if not program.exists() or not step.exists():
            return CADFitResult(
                success=False,
                iou=iou,
                runtime_s=elapsed,
                log=log,
                error="Expected output files missing after CADFit run.",
                metadata=metadata,
            )

        logger.info("CADFit done — IoU: %.4f, time: %.1fs", iou or 0, elapsed)
        return CADFitResult(
            success=True,
            iou=iou,
            runtime_s=elapsed,
            program_path=program,
            step_path=step,
            log=log,
            metadata=metadata,
        )


# ── Mock runner (for development/testing without CADFit) ──────

class MockCADFitRunner:
    """
    Writes dummy output files so the rest of the pipeline can run
    without a real CADFit installation.
    Set CADFIT_MOCK=1 in .env to use this automatically.
    """

    MOCK_PROGRAM = '''\
import cadquery as cq

# Mock CADFit output — simple bracket
result = (
    cq.Workplane("XY")
    .box(100, 60, 10)                       # base plate
    .faces(">Z").workplane()
    .pushPoints([(0, 0)])
    .circle(5).cutThruAll()                 # center hole
    .edges("|Z").fillet(3)                  # edge fillets
)
'''

    MOCK_METRICS = {"iou": 0.91, "runtime_s": 5.0, "mock": True}

    def run(self, mesh_path: Path, output_dir: Path) -> CADFitResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        program_path = output_dir / "program.py"
        step_path = output_dir / "result.step"
        metrics_path = output_dir / "metrics.json"

        program_path.write_text(self.MOCK_PROGRAM, encoding="utf-8")
        metrics_path.write_text(json.dumps(self.MOCK_METRICS, indent=2), encoding="utf-8")

        # Generate a tiny STEP via CadQuery if available, else touch file
        try:
            import cadquery as cq
            box = cq.Workplane("XY").box(100, 60, 10)
            cq.exporters.export(box, str(step_path))
            logger.info("[MockCADFit] Generated STEP via CadQuery.")
        except Exception:
            step_path.touch()
            logger.warning("[MockCADFit] CadQuery unavailable; created empty STEP placeholder.")

        logger.info("[MockCADFit] Mock run complete → IoU=0.91 (fake)")
        return CADFitResult(
            success=True,
            iou=0.91,
            runtime_s=5.0,
            program_path=program_path,
            step_path=step_path,
            log="[mock]",
            metadata=self.MOCK_METRICS,
        )


# ── Factory ───────────────────────────────────────────────────

def get_runner(cadfit_root: Path, mock: bool = False, **kwargs) -> CADFitRunner | MockCADFitRunner:
    """Return real or mock runner based on the *mock* flag / env var."""
    import os
    if mock or os.getenv("CADFIT_MOCK", "0") == "1":
        logger.warning("Using MockCADFitRunner — outputs are synthetic.")
        return MockCADFitRunner()
    return CADFitRunner(cadfit_root=cadfit_root, **kwargs)
