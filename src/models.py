"""Shared data models (Pydantic) used across the entire pipeline."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────

class FeatureType(str, Enum):
    EXTRUDE = "EXTRUDE"
    REVOLVE = "REVOLVE"
    SWEEP = "SWEEP"
    PIPE = "PIPE"
    LOFT = "LOFT"
    CUT = "CUT"
    UNION = "UNION"
    FILLET = "FILLET"
    CHAMFER = "CHAMFER"
    HOLE = "HOLE"
    SHELL = "SHELL"
    DRAFT = "DRAFT"
    PATTERN = "PATTERN"


class ConstraintType(str, Enum):
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    COINCIDENT = "coincident"
    CONCENTRIC = "concentric"
    SYMMETRIC = "symmetric"
    DISTANCE = "distance"
    ANGLE = "angle"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


# ── CAD-IR Building Blocks ─────────────────────────────────────

class GeometryRef(BaseModel):
    """Reference to a geometric entity (face, edge, axis, plane …)."""
    entity_id: str
    entity_type: str  # face | edge | vertex | axis | plane | sketch


class Parameter(BaseModel):
    name: str
    value: float | str
    unit: str = "mm"


class Constraint(BaseModel):
    type: ConstraintType
    entities: list[str]  # entity_ids involved
    value: float | None = None


class CADFeature(BaseModel):
    """A single parametric feature in the CAD construction sequence."""
    id: str
    type: FeatureType
    profile: str | None = None          # Sketch / profile reference: "rectangle", "circle", "cylinder", "pipe", "custom"
    workplane: str = "XY"               # Workplane or face reference ("XY", "XZ", "YZ", ">Z")
    center: list[float] | None = None   # [x, y] or [x, y, z] center position
    depth: float | None = None          # EXTRUDE depth or cut depth
    angle: float | None = None          # REVOLVE angle (deg)
    radius: float | None = None         # FILLET / CHAMFER / Circle radius
    diameter: float | None = None       # HOLE / Cylinder / Pipe outer diameter
    inner_diameter: float | None = None # Pipe / hollow bore inner diameter
    path_points: list[list[float]] | None = None  # Trajectory points for SWEEP/PIPE (e.g. [[x, y], ...])
    path_type: str = "spline"           # "spline" | "arc" | "u_bend" | "straight"
    path_plane: str = "XZ"              # Plane of the sweep trajectory curve
    bolt_circle_diameter: float | None = None  # PCD for circular bolt hole patterns
    hole_count: int | None = None       # Number of holes in pattern
    operation: str = "add"              # "add" (boss/extrude) or "cut" (pocket/hole)
    through_all: bool = False
    direction: list[float] | None = None  # [dx, dy, dz] unit vector
    references: list[GeometryRef] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── CAD-IR Root ────────────────────────────────────────────────

class CADIR(BaseModel):
    """
    CAD Intermediate Representation.
    Contract between CADFit output and SolidWorks/CadQuery adapter.
    """
    part_name: str
    units: str = "mm"
    features: list[CADFeature] = Field(default_factory=list)
    global_constraints: list[Constraint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self, path: Path | None = None) -> str:
        json_str = self.model_dump_json(indent=2)
        if path:
            path.write_text(json_str, encoding="utf-8")
        return json_str

    @classmethod
    def from_json(cls, path: Path) -> "CADIR":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


# ── Validation Report ──────────────────────────────────────────

class DimensionError(BaseModel):
    feature_id: str
    expected: float
    actual: float
    error_mm: float


class ValidationReport(BaseModel):
    status: ValidationStatus
    iou: float | None = None
    chamfer_distance: float | None = None
    dimension_errors: list[DimensionError] = Field(default_factory=list)
    feature_errors: list[str] = Field(default_factory=list)
    notes: str = ""


# ── Mold Analysis ─────────────────────────────────────────────

class DraftFaceResult(BaseModel):
    face_id: str
    draft_angle_deg: float
    status: ValidationStatus  # PASS / WARNING / FAIL (undercut)


class MoldReport(BaseModel):
    parting_direction: list[float]   # unit vector [dx, dy, dz]
    draft_results: list[DraftFaceResult] = Field(default_factory=list)
    undercut_faces: list[str] = Field(default_factory=list)
    parting_line_edges: list[str] = Field(default_factory=list)
    notes: str = ""
