"""
Preliminary Mold Design Module
================================
Analyses a CadQuery-generated solid for injection mold feasibility.

Steps
-----
1. Draft Analysis       — per-face draft angle vs. mold direction
2. Parting Direction    — score candidate directions, pick best
3. Parting Line         — boundary between cavity and core faces
4. Core / Cavity split  — classify faces

All geometry operations use trimesh; heavy OCCT operations
(true core/cavity Boolean) are out of scope for this demo.

Usage:
    analyst = MoldAnalyst()
    report = analyst.analyse(
        mesh_path=Path("demo_part/solidworks/generated.stl"),
        output_dir=Path("demo_part/mold"),
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from src.models import DraftFaceResult, MoldReport, ValidationStatus

logger = logging.getLogger(__name__)

MIN_DRAFT_ANGLE_DEG = 1.0       # faces below this are flagged WARNING
UNDERCUT_THRESHOLD_DEG = -0.5   # faces below this are flagged FAIL (undercut)

# Candidate mold-opening directions to evaluate
_CANDIDATE_DIRECTIONS = [
    [0, 0, 1],   # +Z (top)
    [0, 0, -1],  # -Z (bottom)
    [0, 1, 0],   # +Y
    [0, -1, 0],  # -Y
    [1, 0, 0],   # +X
    [-1, 0, 0],  # -X
]


@dataclass
class MoldAnalysisResult:
    report: MoldReport
    draft_report_path: Path | None = None
    json_report_path: Path | None = None


class MoldAnalyst:
    """Preliminary mold design analyser."""

    def analyse(self, mesh_path: Path, output_dir: Path) -> MoldAnalysisResult:
        output_dir.mkdir(parents=True, exist_ok=True)

        mesh = trimesh.load(str(mesh_path), force="mesh")
        if mesh is None or mesh.is_empty:
            logger.error("Cannot load mesh for mold analysis: %s", mesh_path)
            return MoldAnalysisResult(report=MoldReport(parting_direction=[0, 0, 1]))

        # 1. Find best parting direction
        best_dir, scores = self._find_best_direction(mesh)
        logger.info("Best parting direction: %s (score=%.4f)", best_dir, scores[tuple(best_dir)])

        # 2. Draft analysis along best direction
        draft_results = self._draft_analysis(mesh, best_dir)

        # 3. Parting line (boundary edges between +/- projected faces)
        parting_edges = self._find_parting_line(mesh, best_dir)

        # 4. Undercuts
        undercuts = [r.face_id for r in draft_results if r.status == ValidationStatus.FAIL]

        report = MoldReport(
            parting_direction=best_dir,
            draft_results=draft_results,
            undercut_faces=undercuts,
            parting_line_edges=parting_edges,
            notes=self._summary(draft_results, undercuts, parting_edges),
        )

        # Save outputs
        json_path = output_dir / "mold_report.json"
        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        draft_txt_path = output_dir / "draft_analysis" / "summary.txt"
        draft_txt_path.parent.mkdir(parents=True, exist_ok=True)
        draft_txt_path.write_text(self._draft_text(draft_results), encoding="utf-8")

        logger.info("Mold analysis complete → %s", json_path)
        return MoldAnalysisResult(
            report=report,
            json_report_path=json_path,
            draft_report_path=draft_txt_path,
        )

    # ── Direction scoring ─────────────────────────────────────

    def _find_best_direction(self, mesh: trimesh.Trimesh) -> tuple[list[float], dict]:
        scores: dict[tuple, float] = {}
        for direction in _CANDIDATE_DIRECTIONS:
            d = np.array(direction, dtype=float)
            score = self._score_direction(mesh, d)
            scores[tuple(direction)] = score

        best = max(scores, key=lambda k: scores[k])
        return list(best), {k: v for k, v in scores.items()}

    def _score_direction(self, mesh: trimesh.Trimesh, direction: np.ndarray) -> float:
        """
        Score = fraction of faces with positive draft angle.
        Higher is better.
        """
        normals = mesh.face_normals
        dots = normals @ direction  # cos(angle) for each face
        positive = np.sum(dots > 0)
        return float(positive / len(normals))

    # ── Draft analysis ────────────────────────────────────────

    def _draft_analysis(
        self, mesh: trimesh.Trimesh, direction: list[float]
    ) -> list[DraftFaceResult]:
        d = np.array(direction, dtype=float)
        d /= np.linalg.norm(d)
        results: list[DraftFaceResult] = []

        for i, normal in enumerate(mesh.face_normals):
            dot = float(np.dot(normal, d))
            # Draft angle = angle between face normal and horizontal plane
            angle_deg = float(np.degrees(np.arcsin(np.clip(dot, -1, 1))))

            if angle_deg < UNDERCUT_THRESHOLD_DEG:
                status = ValidationStatus.FAIL
            elif angle_deg < MIN_DRAFT_ANGLE_DEG:
                status = ValidationStatus.WARNING
            else:
                status = ValidationStatus.PASS

            results.append(DraftFaceResult(
                face_id=f"face_{i}",
                draft_angle_deg=round(angle_deg, 3),
                status=status,
            ))

        return results

    # ── Parting line ──────────────────────────────────────────

    def _find_parting_line(self, mesh: trimesh.Trimesh, direction: list[float]) -> list[str]:
        """
        Returns edge IDs that lie on the boundary between faces
        pointing toward vs. away from the mold direction.
        """
        d = np.array(direction, dtype=float)
        face_dots = mesh.face_normals @ d
        face_side = face_dots > 0  # True = cavity side

        parting_edges: list[str] = []
        for edge_idx, faces in enumerate(mesh.face_adjacency):
            if len(faces) < 2:
                continue
            if face_side[faces[0]] != face_side[faces[1]]:
                parting_edges.append(f"edge_{edge_idx}")

        logger.debug("Found %d parting-line edges.", len(parting_edges))
        return parting_edges

    # ── Reporting ─────────────────────────────────────────────

    @staticmethod
    def _summary(draft_results: list[DraftFaceResult], undercuts: list[str], parting_edges: list[str]) -> str:
        pass_count = sum(1 for r in draft_results if r.status == ValidationStatus.PASS)
        warn_count = sum(1 for r in draft_results if r.status == ValidationStatus.WARNING)
        fail_count = len(undercuts)
        return (
            f"Draft: {pass_count} PASS / {warn_count} WARNING / {fail_count} UNDERCUT | "
            f"Parting edges: {len(parting_edges)}"
        )

    @staticmethod
    def _draft_text(results: list[DraftFaceResult]) -> str:
        lines = ["Draft Analysis Report", "=" * 40]
        for r in results:
            lines.append(f"{r.face_id:20s}  {r.draft_angle_deg:+7.2f}°  {r.status}")
        return "\n".join(lines)
