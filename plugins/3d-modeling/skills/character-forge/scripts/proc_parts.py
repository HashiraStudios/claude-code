"""Procedural kit parts: wheels and lamps.

  blender -b --python proc_parts.py -- <out_dir> [wheel|headlight|all]

WHY THESE ARE NOT GENERATED
Image-to-3D reconstruction is excellent at organic bulk and terrible at
small radial mechanical detail. On the off-roader kit the generated wheel
came back with the tyre tread intact but the rim melted into a lump, and
the headlight collapsed into concentric discs — its faceted reflector and
barrel housing gone. Both parts are perfectly regular: a rim is N spokes
on a circle, a reflector is a revolved profile. Regular geometry is
cheaper, sharper and more controllable built by construction.

RULE: radially symmetric hard-surface parts (wheels, lamps, gauges,
bolts, exhausts) are BUILT, not generated. Generation is for the parts
whose shape is genuinely bespoke.

Everything is bevelled chunky to match the Brawl Stars silhouette
language, normalised to height 1.0 and exported as its own GLB, so these
drop into the same kit as the generated parts.
"""
import bpy, bmesh, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT_DIR = argv[0]
WHICH = argv[1] if len(argv) > 1 else "all"
os.makedirs(OUT_DIR, exist_ok=True)


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def mat(name, rgb, rough=0.6, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def bevel(obj, width=0.006, segments=2, angle=50):
    b = obj.modifiers.new("bev", 'BEVEL')
    b.width, b.segments = width, segments
    b.limit_method = 'ANGLE'
    b.angle_limit = math.radians(angle)
    b.harden_normals = True


def join(objs, name):
    # join() keeps ONLY the active object's modifiers and silently drops
    # everyone else's — every bevel would vanish and the part would ship
    # with raw hard edges. Apply them first.
    for o in objs:
        if not o.modifiers:
            continue
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        for m in list(o.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    j = bpy.context.active_object
    j.name = name
    return j


def finish(obj, path):
    """Normalise to height 1.0, centred on the origin, and export."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bb = [Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    s = 1.0 / max((hi - lo).z, 1e-6)
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(scale=True)
    bb = [Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    obj.location = -(lo + hi) / 2
    bpy.ops.object.transform_apply(location=True)
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True)
    print(f"[PROC] {path}  polys={len(obj.data.polygons)}")


# ------------------------------------------------------------------ wheel
def build_wheel(path):
    clear()
    RUBBER = mat("Rubber", (0.11, 0.105, 0.10), rough=0.85)
    RIM = mat("Rim", (0.52, 0.44, 0.30), rough=0.35, metal=0.85)
    DARK = mat("Hub", (0.09, 0.09, 0.10), rough=0.7)
    R_OUT, WIDTH, R_RIM = 0.50, 0.40, 0.28
    parts = []

    # Tyre carcass as an ANNULUS, not a solid disc: a solid cylinder caps
    # the wheel face and hides the rim and spokes completely (which is
    # exactly how the first build came out looking like a plain disc).
    bpy.ops.mesh.primitive_torus_add(
        major_radius=(R_OUT + R_RIM) / 2, minor_radius=(R_OUT - R_RIM) / 2,
        major_segments=48, minor_segments=16)
    tyre = bpy.context.active_object
    # Widen the circular cross-section into a chunky tyre profile. Build it
    # axis-up and scale BEFORE rotating: object scale applies in LOCAL axes,
    # so scaling a primitive that was created pre-rotated stretches the
    # wrong direction — that mistake made the tyre a thin dinner plate.
    tyre.scale = (1, 1, WIDTH / (R_OUT - R_RIM))
    bpy.ops.object.transform_apply(scale=True)
    tyre.rotation_euler = (math.radians(90), 0, 0)
    bpy.ops.object.transform_apply(rotation=True)
    tyre.data.materials.append(RUBBER)
    parts.append(tyre)

    # tread blocks: two staggered rows, which is what reads as "knobby"
    N = 18
    for row, (yoff, phase) in enumerate(((-WIDTH * 0.26, 0.0), (WIDTH * 0.26, 0.5))):
        for i in range(N):
            a = (i + phase) * 2 * math.pi / N
            bpy.ops.mesh.primitive_cube_add(size=1)
            blk = bpy.context.active_object
            blk.scale = (0.075, WIDTH * 0.30, 0.060)
            blk.location = (math.cos(a) * (R_OUT + 0.010), yoff,
                            math.sin(a) * (R_OUT + 0.010))
            blk.rotation_euler = (0, -a, 0)
            blk.data.materials.append(RUBBER)
            bevel(blk, 0.012, 2)
            parts.append(blk)

    # sidewall shoulder lugs
    for i in range(N):
        a = (i + 0.25) * 2 * math.pi / N
        for sgn in (-1, 1):
            bpy.ops.mesh.primitive_cube_add(size=1)
            lug = bpy.context.active_object
            lug.scale = (0.055, 0.03, 0.03)
            lug.location = (math.cos(a) * (R_OUT - 0.05), sgn * WIDTH * 0.48,
                            math.sin(a) * (R_OUT - 0.05))
            lug.rotation_euler = (0, -a, 0)
            lug.data.materials.append(RUBBER)
            bevel(lug, 0.008, 2)
            parts.append(lug)

    # rim dish, recessed so the tyre reads as a separate material band
    bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=R_RIM, depth=WIDTH * 0.55,
                                        rotation=(math.radians(90), 0, 0))
    rim = bpy.context.active_object
    rim.data.materials.append(RIM)
    bevel(rim, 0.02, 3)
    parts.append(rim)

    # six spokes — the detail the generated wheel lost entirely
    for i in range(6):
        a = i * 2 * math.pi / 6
        bpy.ops.mesh.primitive_cube_add(size=1)
        sp = bpy.context.active_object
        sp.scale = (0.21, WIDTH * 0.18, 0.095)
        sp.location = (math.cos(a) * 0.15, -WIDTH * 0.33, math.sin(a) * 0.15)
        sp.rotation_euler = (0, -a, 0)
        sp.data.materials.append(RIM)
        bevel(sp, 0.014, 2)
        parts.append(sp)
        # lug nut between each pair of spokes
        b = (i + 0.5) * 2 * math.pi / 6
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.022, depth=0.05,
                                            rotation=(math.radians(90), 0, 0))
        nut = bpy.context.active_object
        nut.location = (math.cos(b) * 0.115, -WIDTH * 0.41, math.sin(b) * 0.115)
        nut.data.materials.append(DARK)
        bevel(nut, 0.005, 1)
        parts.append(nut)

    # centre cap
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.075, depth=0.10,
                                        rotation=(math.radians(90), 0, 0))
    cap = bpy.context.active_object
    cap.location = (0, -WIDTH * 0.40, 0)
    cap.data.materials.append(DARK)
    bevel(cap, 0.012, 3)
    parts.append(cap)

    finish(join(parts, "wheel"), os.path.join(OUT_DIR, "wheel.glb"))


# -------------------------------------------------------------- headlight
def build_headlight(path):
    clear()
    BEZEL = mat("Bezel", (0.10, 0.10, 0.11), rough=0.55)
    CHROME = mat("Chrome", (0.85, 0.86, 0.88), rough=0.12, metal=1.0)
    GLASS = mat("Lens", (0.86, 0.90, 0.94), rough=0.08)
    parts = []

    # barrel housing behind the lens — the depth the generated one lost
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.34, depth=0.34,
                                        rotation=(math.radians(90), 0, 0))
    barrel = bpy.context.active_object
    barrel.location = (0, 0.20, 0)
    barrel.data.materials.append(BEZEL)
    bevel(barrel, 0.02, 3)
    parts.append(barrel)

    # bezel ring
    bpy.ops.mesh.primitive_torus_add(major_radius=0.45, minor_radius=0.07,
                                     major_segments=40, minor_segments=12,
                                     rotation=(math.radians(90), 0, 0))
    ring = bpy.context.active_object
    ring.data.materials.append(BEZEL)
    parts.append(ring)

    # parabolic reflector, built as a revolved profile so it is a true dish
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.40, radius2=0.06,
                                    depth=0.26, rotation=(math.radians(-90), 0, 0))
    dish = bpy.context.active_object
    dish.location = (0, 0.14, 0)
    dish.data.materials.append(CHROME)
    bevel(dish, 0.01, 2)
    parts.append(dish)

    # radial facets inside the dish: the detail that makes a lamp read as a
    # lamp instead of a disc
    for i in range(16):
        a = i * 2 * math.pi / 16
        bpy.ops.mesh.primitive_cube_add(size=1)
        f = bpy.context.active_object
        f.scale = (0.022, 0.22, 0.16)
        f.location = (math.cos(a) * 0.22, 0.14, math.sin(a) * 0.22)
        f.rotation_euler = (0, -a, 0)
        f.data.materials.append(CHROME)
        bevel(f, 0.006, 1)
        parts.append(f)

    # bulb
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.075, segments=20, ring_count=12)
    bulb = bpy.context.active_object
    bulb.location = (0, 0.10, 0)
    bulb.data.materials.append(CHROME)
    parts.append(bulb)

    # lens: a shallow dome, flattened so it sits proud of the bezel
    # keep the lens INSIDE the bezel so the dish and ring still read; a
    # lens as wide as the bezel just caps the part into a blank disc
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.33, segments=36, ring_count=18)
    lens = bpy.context.active_object
    lens.scale = (1, 0.26, 1)
    lens.location = (0, 0.01, 0)
    lens.data.materials.append(GLASS)
    parts.append(lens)

    finish(join(parts, "headlight"), os.path.join(OUT_DIR, "headlight.glb"))


if WHICH in ("wheel", "all"):
    build_wheel(OUT_DIR)
if WHICH in ("headlight", "all"):
    build_headlight(OUT_DIR)
print("PROC PARTS DONE")
