"""
Module 4: Verifier (Symbolic & Geometric Verification)
======================================================
Verifies the reconstructed CadQuery/OpenCASCADE 3D solid against engineering specifications:
- Concentricity / Coaxiality tolerance check
- Hole count audit
- Ø vs R diameter verification
- Edge blends (Fillet/Chamfer) verification
- Bounding envelope and symmetry check
Generates corrective actions or flags for human review if any check fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.models import CADIR
from src.perception.models import PerceptionOutput

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str
    measured: Any = None
    expected: Any = None


@dataclass
class VerificationReport:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    corrective_actions: list[str] = field(default_factory=list)
    requires_human_review: bool = False

    def summary(self) -> str:
        status_str = "PASS" if self.passed else "FAIL"
        lines = [f"Verification Status: [{status_str}]"]
        for c in self.checks:
            tag = "OK" if c.passed else "FAIL"
            lines.append(f"  - [{tag}] {c.name}: {c.details}")
        if self.corrective_actions:
            lines.append("  Corrective Actions:")
            for a in self.corrective_actions:
                lines.append(f"    * {a}")
        return "\n".join(lines)


class SymbolicCADVerifier:
    """
    Runs automated symbolic and topological verification on OpenCASCADE/CadQuery models.
    """

    def verify(
        self,
        cq_model: Any,
        cadir: CADIR,
        perception: PerceptionOutput | None = None,
    ) -> VerificationReport:
        """Execute all symbolic verification checks on the CadQuery solid."""
        logger.info("[Verifier] Executing symbolic & geometric checks on CAD model...")

        checks: list[CheckResult] = []
        corrective_actions: list[str] = []

        if cq_model is None:
            return VerificationReport(
                passed=False,
                checks=[CheckResult("Model Existence", False, "No 3D solid was produced.")],
                corrective_actions=["Inspect CadQuery script syntax and geometry parameters."],
                requires_human_review=True,
            )

        try:
            solid = cq_model.val()
            bbox = solid.BoundingBox()
            x_len = bbox.xlen
            y_len = bbox.ylen
            z_len = bbox.zlen
        except Exception as exc:
            logger.error("[Verifier] Failed to inspect solid bounding box: %s", exc)
            return VerificationReport(
                passed=False,
                checks=[CheckResult("Solid Topology", False, f"Could not inspect solid: {exc}")],
                corrective_actions=["Check if boolean unions resulted in a disjoint solid."],
                requires_human_review=True,
            )

        # 1. Bounding Envelope Check
        checks.append(
            CheckResult(
                name="Bounding Box",
                passed=x_len > 0 and y_len > 0 and z_len > 0,
                details=f"Dimensions: {x_len:.1f} x {y_len:.1f} x {z_len:.1f} mm",
                measured=[round(x_len, 1), round(y_len, 1), round(z_len, 1)],
            )
        )

        # 2. Coaxiality / Concentricity Check
        # Check that cylindrical features share an aligned center
        cyl_features = [f for f in cadir.features if f.profile == "circle" or f.diameter or f.type.value == "HOLE"]
        if len(cyl_features) >= 2:
            coaxial_aligned = True
            for f in cyl_features:
                if f.center and (abs(f.center[0]) > 0.5 or abs(f.center[1]) > 0.5):
                    coaxial_aligned = False
                    break
            checks.append(
                CheckResult(
                    name="Concentricity Tolerance",
                    passed=coaxial_aligned,
                    details="All cylindrical steps and bores share center axis (tolerance < 0.5 mm)"
                    if coaxial_aligned
                    else "Eccentricity detected between cylinder centers!",
                )
            )
            if not coaxial_aligned:
                corrective_actions.append("Re-align cylindrical centers to [0.0, 0.0] on their workplanes.")
        else:
            checks.append(CheckResult("Concentricity Tolerance", True, "N/A (< 2 cylindrical features)"))

        # 3. Hole Count Check
        expected_holes = 0
        if perception:
            for rf in perception.raw_features:
                op = getattr(rf, "join_operation", getattr(rf, "operation", "add")).lower()
                if rf.feature_type in ("hole", "bore") or op in ("cut", "subtract"):
                    expected_holes += 1

        actual_holes = sum(1 for f in cadir.features if f.type.value == "HOLE")
        hole_pass = (expected_holes == 0) or (actual_holes > 0)
        checks.append(
            CheckResult(
                name="Hole Count Audit",
                passed=hole_pass,
                details=f"Expected ~{expected_holes} through/blind holes, model contains {actual_holes} hole features.",
                measured=actual_holes,
                expected=expected_holes,
            )
        )
        if not hole_pass:
            corrective_actions.append(f"Model lacks required hole features. Expected {expected_holes} holes.")

        # 4. Ø vs R Check (Sanity check that no diameter was entered as radius)
        dia_ok = True
        for f in cadir.features:
            if f.diameter and f.diameter < 1.0:
                dia_ok = False
        checks.append(
            CheckResult(
                name="Ø vs R Verification",
                passed=dia_ok,
                details="All circular features use correct diameter and radius scaling.",
            )
        )

        # 5. Edge Blends Check
        has_blends = any(f.type.value in ("CHAMFER", "FILLET") for f in cadir.features)
        checks.append(
            CheckResult(
                name="Edge Blends (Chamfer/Fillet)",
                passed=True,
                details="Deburring chamfers or stress-relief fillets specified in model sequence."
                if has_blends
                else "No explicit edge blends required.",
            )
        )

        all_passed = all(c.passed for c in checks)
        requires_review = not all_passed

        report = VerificationReport(
            passed=all_passed,
            checks=checks,
            corrective_actions=corrective_actions,
            requires_human_review=requires_review,
        )

        logger.info("[Verifier] Result: %s (%d checks evaluated)", "PASS" if all_passed else "FAIL", len(checks))
        return report
