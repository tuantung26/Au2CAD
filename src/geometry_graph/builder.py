"""
Module 2: Geometry Graph Builder
================================
Constructs a constraint graph from perception output, merges nodes sharing
the same centerline, detects dimensional conflicts, and generates a resolved CAD-IR sequence.
"""

from __future__ import annotations

import logging
from typing import Any
import networkx as nx

from src.models import CADFeature, CADIR, FeatureType
from src.perception.models import PerceptionOutput, RawFeature

logger = logging.getLogger(__name__)


class ConflictReport:
    """Stores detected geometric and dimensional contradictions."""
    def __init__(self) -> None:
        self.conflicts: list[str] = []
        self.warnings: list[str] = []

    def add_conflict(self, msg: str) -> None:
        self.conflicts.append(msg)
        logger.error("[GeometryGraph/Conflict] %s", msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        logger.warning("[GeometryGraph/Warning] %s", msg)

    @property
    def has_errors(self) -> bool:
        return len(self.conflicts) > 0


class GeometryGraphBuilder:
    """
    Builds a directed constraint graph, merges coaxial/centerline nodes,
    validates geometric integrity, and produces a topologically sorted CAD-IR.
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.report = ConflictReport()

    def build_graph(self, perception: PerceptionOutput) -> nx.DiGraph:
        """Construct the constraint graph from raw features and candidate constraints."""
        self.graph.clear()
        self.report = ConflictReport()

        logger.info("[GeometryGraph] Constructing constraint graph for '%s'...", perception.part_name)

        # 1. Add feature nodes
        for rf in perception.raw_features:
            self.graph.add_node(
                rf.id,
                feature_type=rf.feature_type.lower(),
                description=rf.description,
                quantity=rf.quantity,
                dimensions=rf.dimensions,
                axis=rf.axis_or_centerline,
                parent=rf.parent_feature,
                face=rf.attachment_face.lower(),
                join_op=rf.join_operation.lower(),
                offset=rf.relative_offset or [0.0, 0.0, 0.0],
                view_source=rf.view_source,
                primary_source=rf.primary_source,
                raw=rf,
            )

            # Add structural parent-child assembly edge
            if rf.parent_feature and self.graph.has_node(rf.parent_feature):
                self.graph.add_edge(
                    rf.parent_feature,
                    rf.id,
                    constraint_type="assembly_join",
                    interface_face=rf.attachment_face,
                    operation=rf.join_operation,
                )

        # 2. Add constraint edges
        for cc in perception.candidate_constraints:
            if len(cc.features) >= 2:
                for i in range(len(cc.features) - 1):
                    u = cc.features[i]
                    v = cc.features[i + 1]
                    if self.graph.has_node(u) and self.graph.has_node(v):
                        self.graph.add_edge(u, v, constraint_type=cc.type.lower(), datum=cc.datum, note=cc.note)
            elif len(cc.features) == 1 and cc.datum:
                u = cc.features[0]
                if self.graph.has_node(u):
                    self.graph.nodes[u]["datum"] = cc.datum

        # 3. Merge nodes sharing the same centerline
        self._merge_centerlines(perception)

        # 4. Check for dimensional conflicts
        self._detect_conflicts(perception)

        logger.info(
            "[GeometryGraph] Graph built: %d nodes, %d edges, %d conflicts detected.",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
            len(self.report.conflicts),
        )

        return self.graph

    def _merge_centerlines(self, perception: PerceptionOutput) -> None:
        """Link and align features sharing the same centerline axis into coaxial groups."""
        centerline_groups: dict[str, list[str]] = {}

        for node_id, data in self.graph.nodes(data=True):
            axis = data.get("axis")
            if axis:
                centerline_groups.setdefault(axis, []).append(node_id)

        for axis_name, members in centerline_groups.items():
            if len(members) > 1:
                logger.info("[GeometryGraph] Merging coaxial features on centerline '%s': %s", axis_name, members)
                for i in range(len(members) - 1):
                    u, v = members[i], members[i + 1]
                    if not self.graph.has_edge(u, v):
                        self.graph.add_edge(u, v, constraint_type="coaxial", axis=axis_name)

    def _detect_conflicts(self, perception: PerceptionOutput) -> None:
        """Detect contradictory dimensions such as hole diameter > body diameter, negative dims, etc."""
        cylinders: list[tuple[str, float]] = []
        bores: list[tuple[str, float]] = []

        for node_id, data in self.graph.nodes(data=True):
            dims = data.get("dimensions", {})

            # Check negative dimensions
            for dim_name, val in dims.items():
                if val <= 0:
                    self.report.add_conflict(f"Node {node_id}: Dimension '{dim_name}' must be positive, got {val}")

            ftype = data.get("feature_type", "")
            if ftype in ("cylinder", "pipe", "shaft", "boss"):
                dia = dims.get("diameter", dims.get("outer_diameter", 0.0))
                if dia > 0:
                    cylinders.append((node_id, dia))
            elif ftype in ("bore", "hole"):
                dia = dims.get("diameter", dims.get("inner_diameter", 0.0))
                if dia > 0:
                    bores.append((node_id, dia))

        # Check bore inside cylinder conflict
        if cylinders and bores:
            min_outer_dia = min(d for _, d in cylinders)
            max_inner_bore = max(d for _, d in bores)
            if max_inner_bore >= min_outer_dia:
                self.report.add_conflict(
                    f"Contradictory dimensions: Maximum inner bore ({max_inner_bore} mm) "
                    f"is >= minimum outer cylinder diameter ({min_outer_dia} mm)!"
                )

    def resolve_to_cadir(self, perception: PerceptionOutput) -> CADIR:
        """
        Translates the verified constraint graph into a standard CAD-IR model
        following the expected CAD execution sequence.
        """
        cad_features: list[CADFeature] = []

        # CAD Execution Sequence:
        # 1. Base solid roots (box / main boss)
        # 2. Additive children (bosses, cylinders, ribs)
        # 3. Subtractive features (bores, holes, notches, cutouts)
        # 4. Edge blends (chamfers, fillets)
        def feature_priority(node_id: str) -> int:
            data = self.graph.nodes[node_id]
            ftype = data.get("feature_type", "")
            op = data.get("join_op", data.get("operation", "add"))
            if op == "add":
                if ftype in ("box", "block") or not data.get("parent"):
                    return 1
                return 2
            elif op == "subtract" or op == "cut" or ftype in ("hole", "bore", "slot", "notch", "cutout"):
                return 3
            elif op == "blend" or ftype in ("chamfer", "fillet"):
                return 4
            return 5

        sorted_node_ids = sorted(self.graph.nodes(), key=feature_priority)

        # Mapping of attachment_face to CadQuery workplane selector
        face_map = {
            "root": "XY",
            "top": ">Z",
            "bottom": "<Z",
            "front": ">Y",
            "rear": "<Y",
            "side": ">X",
            "coaxial": ">Z",
        }

        for node_id in sorted_node_ids:
            data = self.graph.nodes[node_id]
            ftype = data.get("feature_type", "")
            dims = data.get("dimensions", {})
            face = data.get("face", "top")
            wp = face_map.get(face, ">Z")
            offset = data.get("offset", [0.0, 0.0, 0.0])
            center_2d = [offset[0], offset[1]] if len(offset) >= 2 else [0.0, 0.0]

            if ftype in ("box", "block"):
                l = dims.get("length", 100.0)
                w = dims.get("width", 62.0)
                h = dims.get("height", dims.get("depth", 18.0))
                cad_features.append(
                    CADFeature(
                        id=node_id,
                        type=FeatureType.EXTRUDE,
                        profile="rectangle",
                        workplane="XY" if not data.get("parent") else wp,
                        center=center_2d,
                        depth=h,
                        operation="add",
                        metadata={"length": l, "width": w, "height": h, "tag": f"tagged_{node_id}"},
                    )
                )

            elif ftype in ("cylinder", "shaft", "boss"):
                dia = dims.get("diameter", dims.get("outer_diameter", 44.0))
                length = dims.get("length", dims.get("height", 40.0))
                cad_features.append(
                    CADFeature(
                        id=node_id,
                        type=FeatureType.EXTRUDE,
                        profile="circle",
                        workplane=wp,
                        center=center_2d,
                        diameter=dia,
                        depth=length,
                        operation="add",
                        metadata={"tag": f"tagged_{node_id}"},
                    )
                )

            elif ftype in ("bore", "hole"):
                dia = dims.get("diameter", dims.get("inner_diameter", 28.0))
                cad_features.append(
                    CADFeature(
                        id=node_id,
                        type=FeatureType.HOLE,
                        workplane=wp,
                        center=center_2d,
                        diameter=dia,
                        through_all=True,
                        operation="cut",
                        metadata={"tag": f"tagged_{node_id}"},
                    )
                )

            elif ftype in ("slot", "pocket", "notch", "cutout"):
                w = dims.get("width", 28.0)
                d = dims.get("depth", dims.get("height", 9.0))
                l = dims.get("length", 100.0)
                cad_features.append(
                    CADFeature(
                        id=node_id,
                        type=FeatureType.CUT,
                        profile="rectangle",
                        workplane=wp,
                        center=center_2d,
                        depth=d,
                        operation="cut",
                        metadata={"width": w, "length": l, "depth": d},
                    )
                )

            elif ftype == "chamfer":
                size = dims.get("size", dims.get("chamfer", 10.0))
                cad_features.append(
                    CADFeature(
                        id=node_id,
                        type=FeatureType.CHAMFER,
                        radius=size,
                        workplane="XY",
                        metadata={"edges": "|Z"},
                    )
                )

            elif ftype == "fillet":
                r = dims.get("radius", dims.get("r", 5.0))
                cad_features.append(
                    CADFeature(
                        id=node_id,
                        type=FeatureType.FILLET,
                        radius=r,
                        workplane="XY",
                        metadata={"edges": "|Z"},
                    )
                )

        return CADIR(
            part_name=perception.part_name,
            features=cad_features,
            metadata={"conflicts": self.report.conflicts, "warnings": self.report.warnings},
        )
