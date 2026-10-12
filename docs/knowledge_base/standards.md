# Engineering Drawing Interpretation & CAD Modeling Standards

## 1. Principles of Technical Drawing Interpretation

An engineering drawing often comprises multiple orthographic and section views taken from different projection angles.  
Each view is **not an isolated component**, but a representation of a **single unified physical object in 3D coordinate space**.

- **Orthographic Views (Front / Top / Side):** Define the outer boundary, overall envelope, and external morphology.
- **Section Views (e.g., A–A):** Reveal internal cavities, stepped bores, wall thicknesses, and hidden features.
- **Auxiliary & Detail Views (e.g., View B):** Specify hole patterns, underside geometries, flanges, or local details.
- **Centerlines (Axis of Symmetry):** Define coaxiality, symmetry planes, and critical datum references.

> **Key Takeaway:** When synthesizing CAD models from 2D drawings, **all views must be integrated holistically** to reconstruct one coherent 3D solid. Never treat separate views as disjoint parts.

---

## 2. Rules for CAD Reconstruction from Engineering Blueprints

### Rule 1 — Read Multi-View Projections as a Unified Solid
- Reconstruct all projections within a shared 3D coordinate frame.
- Combine the front view (overall profile), section A–A (internal structure), and auxiliary views (mounting holes) into a single part.

### Rule 2 — Centerlines Are Geometric Datums
- Centerlines represent functional engineering axes, not decorative marks.
- They identify:
  - Hole centers
  - Pipe & cylinder axes
  - Centers of revolution
  - Planes of symmetry
- Primary inlet and circular body axes serve as critical reference datums.

### Rule 3 — Symbol Ø Denotes Diameter, Not Radius
- `Ø100` $\rightarrow$ Diameter of 100 mm.
- `R10` $\rightarrow$ Radius of 10 mm.
- Never model a circular arc with radius $R = 100\text{ mm}$ when the drawing specifies $\text{Ø}100$.

### Rule 4 — Notation `n × Ød` or `Ød — n отв.` Represents a Hole Pattern
- Example: `Ø10 — 4 отв.` (Russian *отв.* = holes) $\rightarrow$ 4 separate holes, each $\text{Ø}10\text{ mm}$.
- Do not interpret this as a single $\text{Ø}40\text{ mm}$ bore.

### Rule 5 — Concentric Circles Must Be Strictly Coaxial
- Diameters such as $\text{Ø}40$, $\text{Ø}60$, $\text{Ø}80$, and $\text{Ø}100$ must share an identical center axis.
- Avoid locating centers manually; enforce coaxial constraints for proper assembly mating, CAM toolpaths, FEA simulation, and STEP export.

### Rule 6 — Section Hatching Represents Solid Material
- In section cuts (e.g., A–A):
  - **Cross-hatch pattern:** Solid material volume.
  - **Non-hatched areas:** Internal voids, through-holes, or cavities.
- Never fill an entire section view as a monolithic solid block.

### Rule 7 — Hidden Lines Are Occluded Boundaries
- Dashed lines indicate occluded rear surfaces, blind holes, or interior walls.
- Do not mistake hidden lines for external grooves or surface cuts.

### Rule 8 — Transition Fillets Must Maintain Tangency
- Fillet arcs (e.g., $R5$, $R10$) must blend tangentially with adjacent planar and curved faces.
- Critical for cast components to prevent stress concentrations and sharp corners.

### Rule 9 — Symmetrical Geometries Must Be Truly Symmetric
- Enforce symmetry across:
  - Central circular features
  - Bolt hole patterns
  - Mounting lugs / ears
- Do not construct opposite sides independently when a symmetry plane is present.

### Rule 10 — Never Hallucinate Missing Dimensions
- Never guess CAD dimensions by measuring screen pixels if an explicit value is omitted.
- Infer missing geometry strictly through geometric constraints, and clearly flag assumed values as `assumed dimension`.

---

## 3. Mandatory Geometric Constraints in CAD

A robust parametric model requires explicit geometric constraints:

| Constraint | Technical Definition | Engineering Purpose |
| :--- | :--- | :--- |
| **Concentric / Coaxial** | Common center / shared rotational axis | Multi-stage cylindrical shafts and bores |
| **Coincident** | Points or edges aligned on the same entity | Accurate vertex and edge connectivity |
| **Tangent** | Smooth transitions between arcs and lines | Fillets, blends, and aerodynamic/fluid flow paths |
| **Symmetric** | Equal mirror geometry across a datum plane | Balanced mass distribution and simplified modeling |
| **Horizontal / Vertical**| Alignment along principal coordinate axes | Stable, fully defined 2D sketches |
| **Equal** | Matching sizes across identical features | Uniform ribs, pockets, and wall thicknesses |
| **Pattern** | Circular (PCD) or linear feature repetition | Bolt circle holes and heatsink fins |

---

## 4. Design for Manufacturing (DFM) & Process Considerations

### Casting vs. CNC Machining Characteristics
Complex components with organic blends, internal cavities, mounting flanges, and thick walls typically originate as **castings** (e.g., sand or investment cast housings) followed by finish machining:
- **As-cast features:** Curved outer walls, generous fillets ($R5$–$R10$), draft angles, and raw cored cavities.
- **Finish-machined features:** Flange mating faces, precision counterbores, bearing seats, and sealing grooves.
- When materials, dimensional tolerances, and surface roughness are unspecified, adhere to nominal geometry without arbitrarily imposing unstated tolerances.

---

## 5. General Machining & Fastener Standards

### Holes & Fasteners
- **Clearance Holes:** For standard M10 bolts, drill diameter must be $\ge 10.0\text{ mm}$ (close fit) or $10.5\text{ mm}$ (normal/clearance fit). Never design $< 10.0\text{ mm}$.
- **Internal Pocket Fillets:** Internal vertical corner radii must accommodate standard milling endmill radii (minimum $R \ge 2.0\text{ mm}$).

### Dimension Normalization
- Standard stock thicknesses follow preferred numbers (multiples of 5 mm: 5, 10, 15, 20 mm).
- Measurement noise from 3D scans (e.g., 4.87 mm or 5.12 mm) must be rounded to standard nominal values (5.0 mm).

### Edge Treatments
- External functional edges should feature deburring chamfers ($1\times45^\circ$ or $2\times45^\circ$) or edge breaks to eliminate sharp burrs.

---
