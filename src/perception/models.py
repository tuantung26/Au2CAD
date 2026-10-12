"""
Module 1: Perception / Parser Data Models
=========================================
Structured representations of drawing perception output before graph construction.
Enforces exhaustive shape inventory, exact quantities, and assembly/joining topology.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class RawFeature(BaseModel):
    """
    A concrete geometric shape extracted directly from the engineering blueprint.
    Contains exhaustive dimensional data, quantities, and attachment interfaces.
    """
    id: str
    feature_type: str                     # "box", "cylinder", "bore", "hole", "slot", "notch", "rib", "cutout", "chamfer", "fillet"
    description: str = ""
    quantity: int = 1                     # Number of instances of this primitive shape
    dimensions: dict[str, float] = Field(default_factory=dict)  # {"length": ..., "width": ..., "diameter": ..., etc.}
    
    # ── Assembly & Joining Topology ───────────────────────────
    parent_feature: str | None = None     # ID of the base shape this attaches to / cuts from (None if root base)
    attachment_face: str = "top"          # "top" (>Z), "bottom" (<Z), "front" (>Y), "rear" (<Y), "side" (>X), "coaxial"
    join_operation: str = "ADD"           # "ADD" (union/boss), "SUBTRACT" (pocket/hole/cut), "BLEND" (fillet/chamfer)
    operation: str = "add"                # Compatibility alias ("add", "cut", "blend")
    relative_offset: list[float] | None = None  # [dx, dy, dz] offset relative to parent reference datum
    
    # ── Datum & Source Integrity ──────────────────────────────
    axis_or_centerline: str | None = None # Linked centerline / rotational axis
    view_source: str = "blueprint"        # "top_view", "front_view", "side_view", "section_A-A"
    primary_source: str = "drawing"       # "drawing" (Primary Single Source of Truth) or "description" (Auxiliary)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateConstraint(BaseModel):
    """A geometric constraint proposed by perception before graph validation."""
    type: str                             # "coaxial", "concentric", "symmetric", "tangent", "attached_to", "coincident"
    features: list[str] = Field(default_factory=list)  # Feature IDs involved
    datum: str | None = None              # Name of reference datum or axis
    value: float | None = None            # Offset distance or angle
    note: str = ""


class PerceptionOutput(BaseModel):
    """
    Contract of Module 1 (Perception / Parser).
    The blueprint drawing is strictly designated as the Primary Single Source of Truth (SSOT).
    Contains exhaustive shape counts and topological assembly instructions.
    """
    part_name: str = "MechanicalPart"
    overview: str = ""
    drawing_is_primary_truth: bool = True # True = Blueprint drawing drives 100% of geometry
    centerlines: list[str] = Field(default_factory=list)
    raw_features: list[RawFeature] = Field(default_factory=list)
    candidate_constraints: list[CandidateConstraint] = Field(default_factory=list)
    assembly_join_sequence: list[str] = Field(default_factory=list) # Ordered sequence of joining operations
    metadata: dict[str, Any] = Field(default_factory=dict)
