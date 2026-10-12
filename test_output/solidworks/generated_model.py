import cadquery as cq

# Parametric Support Bracket derived directly from Blueprint Dimensions (SSOT)
# Units: mm
length = 100.0          # Base length from rear face to center of front cutout
width = 62.0            # Base overall transverse span
base_height = 18.0      # Base vertical thickness
r22 = 22.0              # Front semicircular cutout radius
notch_width = 28.0      # Bottom slot width
notch_depth = 9.0       # Bottom slot depth
notch_offset = 8.0      # Bottom slot offset from rear face
boss_od = 44.0          # Upper boss outer diameter
boss_id = 28.0          # Upper boss inner bore diameter
boss_center_height = 50.0  # Center height from bottom base datum
side_wall_thick = 9.0   # Left/right outer wall thickness

# 1. Base Block
base = cq.Workplane("XY").box(width, length, base_height, centered=(True, False, False))

# 2. Front R22 Semicircular Cutout
front_cut = (
    cq.Workplane("XY")
    .transformed(offset=cq.Vector(0, length, 0))
    .cylinder(base_height * 2, r22, centered=(True, True, True))
)
base = base.cut(front_cut)

# 3. Bottom Underside Notch
notch = (
    cq.Workplane("YZ")
    .transformed(offset=cq.Vector(notch_offset, 0, 0))
    .box(notch_width, notch_depth, width + 10.0, centered=(False, False, True))
)
base = base.cut(notch)

# 4. Upper Cylindrical Boss
boss_radius = boss_od / 2.0
boss_center_y = boss_radius  # Flush with rear face
boss = (
    cq.Workplane("YZ")
    .transformed(offset=cq.Vector(boss_center_y, boss_center_height, 0))
    .circle(boss_radius)
    .extrude(width, both=True)
)

# 5. Through-Bore in Boss
bore = (
    cq.Workplane("YZ")
    .transformed(offset=cq.Vector(boss_center_y, boss_center_height, 0))
    .circle(boss_id / 2.0)
    .extrude(width + 20.0, both=True)
)
boss = boss.cut(bore)

# 6. Sloped Transition Web / Rib
central_width = width - (2.0 * side_wall_thick)
web_profile = (
    cq.Workplane("YZ")
    .polyline([
        (boss_center_y - boss_radius, boss_center_height),
        (boss_center_y + boss_radius, boss_center_height - boss_radius),
        (length - r22, base_height),
        (0.0, base_height)
    ])
    .close()
    .extrude(central_width, both=True)
)

# 7. Final Solid Assembly
result = base.union(boss).union(web_profile)
