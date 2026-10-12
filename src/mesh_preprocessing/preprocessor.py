"""
Mesh Preprocessing Pipeline
============================
Steps (in order):
  1. Load mesh (trimesh)
  2. Remove duplicate / degenerate faces
  3. Fill holes → watertight
  4. Taubin smoothing
  5. Decimation (target face count)
  6. Scale alignment (normalize or apply known scale)
  7. Export clean mesh

Usage (CLI):
    python -m src.mesh_preprocessing.preprocessor \
        --input demo_part/reconstruction/raw_mesh.obj \
        --output demo_part/reconstruction/clean_mesh.obj \
        --target-faces 50000
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import trimesh

logger = logging.getLogger(__name__)


class MeshPreprocessor:
    """
    Encapsulates the full preprocessing pipeline.
    Returns a cleaned trimesh.Trimesh ready for CADFit.
    """

    def __init__(
        self,
        target_faces: int = 50_000,
        smooth_iterations: int = 10,
        smooth_lambda: float = 0.5,
        smooth_nu: float = -0.53,
    ) -> None:
        self.target_faces = target_faces
        self.smooth_iterations = smooth_iterations
        self.smooth_lambda = smooth_lambda
        self.smooth_nu = smooth_nu

    # ── Public API ────────────────────────────────────────────

    def run(self, input_path: Path, output_path: Path | None = None) -> trimesh.Trimesh:
        """
        Full preprocessing pipeline.
        Returns the processed mesh and optionally saves it.
        """
        logger.info("Loading mesh: %s", input_path)
        mesh = trimesh.load(str(input_path), force="mesh")

        mesh = self._remove_degenerate(mesh)
        mesh = self._fill_holes(mesh)
        mesh = self._smooth(mesh)
        mesh = self._decimate(mesh)

        logger.info(
            "Preprocessing complete → faces: %d, watertight: %s",
            len(mesh.faces),
            mesh.is_watertight,
        )

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            mesh.export(str(output_path))
            logger.info("Saved clean mesh → %s", output_path)

        return mesh

    def get_stats(self, mesh: trimesh.Trimesh) -> dict:
        return {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "is_watertight": mesh.is_watertight,
            "volume_mm3": float(mesh.volume) if mesh.is_watertight else None,
            "bounds_mm": mesh.bounds.tolist(),
        }

    # ── Steps ─────────────────────────────────────────────────

    def _remove_degenerate(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        logger.debug("Removing degenerate faces and duplicates …")
        mesh.remove_degenerate_faces()
        mesh.remove_duplicate_faces()
        mesh.remove_unreferenced_vertices()
        mesh.fix_normals()
        return mesh

    def _fill_holes(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        logger.debug("Filling holes to make mesh watertight …")
        # trimesh fill_holes works on a copy
        filled = trimesh.repair.fill_holes(mesh)
        if filled is not None and isinstance(filled, trimesh.Trimesh):
            mesh = filled
        trimesh.repair.fix_winding(mesh)
        trimesh.repair.fix_inversion(mesh)
        return mesh

    def _smooth(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Taubin smoothing (reduces shrinkage vs. Laplacian)."""
        logger.debug(
            "Taubin smoothing: %d iterations, λ=%.2f, ν=%.2f …",
            self.smooth_iterations,
            self.smooth_lambda,
            self.smooth_nu,
        )
        try:
            smoothed = trimesh.smoothing.filter_taubin(
                mesh,
                lamb=self.smooth_lambda,
                nu=self.smooth_nu,
                iterations=self.smooth_iterations,
            )
            return smoothed
        except Exception as exc:
            logger.warning("Taubin smoothing failed (%s); skipping.", exc)
            return mesh

    def _decimate(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Reduce face count while preserving shape."""
        current = len(mesh.faces)
        if current <= self.target_faces:
            logger.debug("Decimation skipped (faces %d ≤ target %d).", current, self.target_faces)
            return mesh
        ratio = self.target_faces / current
        logger.debug("Decimating: %d → ~%d faces (ratio=%.3f) …", current, self.target_faces, ratio)
        try:
            decimated = mesh.simplify_quadric_decimation(self.target_faces)
            return decimated
        except Exception as exc:
            logger.warning("Decimation failed (%s); returning original.", exc)
            return mesh


# ── CLI entry point ────────────────────────────────────────────

def _main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Mesh Preprocessing Pipeline")
    parser.add_argument("--input", required=True, type=Path, help="Raw mesh file (.obj/.stl/.ply)")
    parser.add_argument("--output", type=Path, default=None, help="Output clean mesh path")
    parser.add_argument("--target-faces", type=int, default=50_000)
    parser.add_argument("--smooth-iterations", type=int, default=10)
    args = parser.parse_args()

    preprocessor = MeshPreprocessor(
        target_faces=args.target_faces,
        smooth_iterations=args.smooth_iterations,
    )
    mesh = preprocessor.run(args.input, args.output)
    import json, sys
    print(json.dumps(preprocessor.get_stats(mesh), indent=2))


if __name__ == "__main__":
    _main()
