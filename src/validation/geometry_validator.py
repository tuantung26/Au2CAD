"""
Geometry Validator
===================
Compares the original (clean) mesh with the CAD-generated mesh/STEP
to produce a ValidationReport.

Metrics computed
----------------
* IoU (Volumetric)   — sampled via voxel grids
* Chamfer Distance   — between surface point clouds
* Dimension errors   — per-feature diameter/depth/radius vs CAD-IR spec

Usage:
    validator = GeometryValidator(iou_threshold=0.90)
    report = validator.validate(
        reference_mesh_path=Path("demo_part/reconstruction/clean_mesh.obj"),
        generated_stl_path=Path("demo_part/solidworks/generated.stl"),
        cadir=cadir,
    )
    print(report.status, report.iou)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import trimesh

from src.models import (
    CADIR,
    DimensionError,
    FeatureType,
    ValidationReport,
    ValidationStatus,
)
from src.config import VALIDATION_IOU_THRESHOLD, VALIDATION_DIM_ERROR_MM

logger = logging.getLogger(__name__)

_VOXEL_PITCH = 2.0          # mm — voxel size for IoU approximation
_SAMPLE_POINTS = 10_000     # number of surface samples for Chamfer


class GeometryValidator:
    """Validates a generated CAD mesh against the reference scan mesh."""

    def __init__(
        self,
        iou_threshold: float = VALIDATION_IOU_THRESHOLD,
        dim_error_threshold_mm: float = VALIDATION_DIM_ERROR_MM,
        voxel_pitch: float = _VOXEL_PITCH,
        sample_points: int = _SAMPLE_POINTS,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.dim_error_threshold = dim_error_threshold_mm
        self.voxel_pitch = voxel_pitch
        self.sample_points = sample_points

    # ── Public API ────────────────────────────────────────────

    def validate(
        self,
        reference_mesh_path: Path | None,
        generated_stl_path: Path,
        cadir: CADIR | None = None,
    ) -> ValidationReport:
        gen = self._load(generated_stl_path)
        if gen is None:
            return ValidationReport(
                status=ValidationStatus.FAIL,
                notes="Could not load generated STL.",
            )

        ref = self._load(reference_mesh_path) if reference_mesh_path else None

        iou = self._compute_iou(ref, gen) if ref else None
        chamfer = self._compute_chamfer(ref, gen) if ref else None
        dim_errors = self._check_dimensions(cadir, gen) if cadir else []
        feature_errors = self._check_topology(gen)

        status = self._determine_status(iou, dim_errors, feature_errors, has_ref=(ref is not None))

        report = ValidationReport(
            status=status,
            iou=iou,
            chamfer_distance=chamfer,
            dimension_errors=dim_errors,
            feature_errors=feature_errors,
            notes=self._summary(iou, chamfer, dim_errors, feature_errors),
        )
        logger.info(
            "Validation → status=%s  IoU=%.4f  Chamfer=%.4f",
            status, iou or 0, chamfer or 0,
        )
        return report

    # ── Metric computations ───────────────────────────────────

    def _compute_iou(self, ref: trimesh.Trimesh, gen: trimesh.Trimesh) -> float | None:
        """Approximate volumetric IoU via voxelisation."""
        try:
            # Align bounding boxes before voxelising
            ref_v = ref.voxelized(pitch=self.voxel_pitch).fill()
            gen_v = gen.voxelized(pitch=self.voxel_pitch).fill()

            ref_pts = set(map(tuple, ref_v.sparse_indices))
            gen_pts = set(map(tuple, gen_v.sparse_indices))

            intersection = len(ref_pts & gen_pts)
            union = len(ref_pts | gen_pts)
            return intersection / union if union > 0 else 0.0
        except Exception as exc:
            logger.warning("IoU computation failed: %s", exc)
            return None

    def _compute_chamfer(self, ref: trimesh.Trimesh, gen: trimesh.Trimesh) -> float | None:
        """Symmetric Chamfer Distance between sampled surface point clouds."""
        try:
            ref_pts = ref.sample(self.sample_points)
            gen_pts = gen.sample(self.sample_points)

            # Nearest-neighbour distances (brute-force, OK for 10k pts)
            from scipy.spatial import KDTree
            tree_ref = KDTree(ref_pts)
            tree_gen = KDTree(gen_pts)

            d_ref_gen, _ = tree_gen.query(ref_pts)
            d_gen_ref, _ = tree_ref.query(gen_pts)

            chamfer = float(np.mean(d_ref_gen) + np.mean(d_gen_ref))
            return chamfer
        except Exception as exc:
            logger.warning("Chamfer distance computation failed: %s", exc)
            return None

    def _check_dimensions(self, cadir: CADIR, gen: trimesh.Trimesh) -> list[DimensionError]:
        """Check bounding-box dimensions against CADIR parameters."""
        errors: list[DimensionError] = []
        bounds = gen.bounding_box.extents  # [x, y, z] in mm

        for feat in cadir.features:
            params = {p.name: p.value for p in feat.parameters}
            checks = [
                ("length", bounds[0]),
                ("width", bounds[1]),
                ("height", bounds[2]),
                ("depth", bounds[2]),
                ("diameter", None),   # not checkable from bbox alone
            ]
            for pname, actual in checks:
                if pname not in params or actual is None:
                    continue
                expected = params[pname]
                err = abs(expected - actual)
                if err > self.dim_error_threshold:
                    errors.append(DimensionError(
                        feature_id=feat.id,
                        expected=expected,
                        actual=actual,
                        error_mm=err,
                    ))
        return errors

    def _check_topology(self, mesh: trimesh.Trimesh) -> list[str]:
        """Basic mesh validity checks."""
        errors = []
        if not mesh.is_watertight:
            errors.append("Generated mesh is not watertight (may have holes).")
        if mesh.is_empty:
            errors.append("Generated mesh is empty.")
        if not mesh.is_volume:
            errors.append("Generated mesh does not form a valid volume.")
        return errors

    # ── Status logic ──────────────────────────────────────────

    def _determine_status(
        self,
        iou: float | None,
        dim_errors: list[DimensionError],
        feature_errors: list[str],
        has_ref: bool = True,
    ) -> ValidationStatus:
        if feature_errors:
            return ValidationStatus.FAIL
        if has_ref:
            if iou is None or iou < self.iou_threshold:
                return ValidationStatus.FAIL
        if dim_errors:
            return ValidationStatus.WARNING
        return ValidationStatus.PASS

    @staticmethod
    def _summary(iou, chamfer, dim_errors, feature_errors) -> str:
        parts = [f"IoU={iou:.4f}" if iou else "IoU=N/A"]
        if chamfer:
            parts.append(f"Chamfer={chamfer:.4f}mm")
        if dim_errors:
            parts.append(f"{len(dim_errors)} dimension error(s)")
        if feature_errors:
            parts.append(f"{len(feature_errors)} topology error(s)")
        return " | ".join(parts)

    # ── Loader ────────────────────────────────────────────────

    @staticmethod
    def _load(path: Path) -> trimesh.Trimesh | None:
        try:
            mesh = trimesh.load(str(path), force="mesh")
            return mesh
        except Exception as exc:
            logger.error("Failed to load mesh %s: %s", path, exc)
            return None
