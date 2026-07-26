"""Contact sheet of a kit: every part rendered in a labelled grid.

  blender -b --python kit_sheet.py -- <parts_dir> <parts.json> <out.png> [clay]

One image showing what the kit contains, each piece named and with its
quantity, so the person assembling can see the whole inventory at a
glance instead of opening ten files. Pass `clay` to render bare geometry
(the QA read) instead of textures (the delivery read).

Each part is scaled to fit its cell, so the sheet shows SHAPE, not
relative size — relative size lives in the placement manifest.
"""
import bpy, sys, os, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
PARTS_DIR, MANIFEST, OUT = argv[0], argv[1], argv[2]
CLAY = len(argv) > 3 and argv[3] == "clay"

man = json.load(open(MANIFEST))
labels = {p["id"]: (p.get("label", p["id"]), p.get("qty", 1)) for p in man["parts"]}

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

files = sorted(f for f in os.listdir(PARTS_DIR) if f.endswith((".glb", ".gltf")))
if not files:
    raise SystemExit(f"no part meshes in {PARTS_DIR}")
cols = min(4, len(files))
rows = math.ceil(len(files) / cols)
CELL = 2.4
print(f"[SHEET] {len(files)} parts in {cols}x{rows}")

clay_mat = bpy.data.materials.new("Clay")
clay_mat.use_nodes = True
_b = clay_mat.node_tree.nodes["Principled BSDF"]
_b.inputs["Base Color"].default_value = (0.62, 0.60, 0.58, 1)
_b.inputs["Roughness"].default_value = 0.62

for i, fn in enumerate(files):
    pid = os.path.splitext(fn)[0]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(PARTS_DIR, fn))
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if not new:
        continue
    obj = max(new, key=lambda o: len(o.data.polygons))
    for o in new:
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bb = [Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[k] for v in bb) for k in range(3)))
    hi = Vector((max(v[k] for v in bb) for k in range(3)))
    span = max(hi - lo)
    s = (CELL * 0.42) / max(span, 1e-6)      # every part fills its cell
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    # lay the grid on a VERTICAL wall (XZ) and shoot it straight on: a
    # tilted floor grid foreshortens the rows and wastes most of the frame
    cx = (i % cols - (cols - 1) / 2) * CELL
    cz = -(i // cols - (rows - 1) / 2) * CELL
    mid = (lo + hi) / 2 * s
    obj.location = (cx - mid.x, -mid.y, cz - mid.z + CELL * 0.06)
    if CLAY:
        obj.data.materials.clear()
        obj.data.materials.append(clay_mat)

    label, qty = labels.get(pid, (pid, 1))
    txt = bpy.data.curves.new(pid, 'FONT')
    txt.body = f"{label}" + (f"  x{qty}" if qty > 1 else "")
    txt.size = 0.16
    txt.align_x = 'CENTER'
    to = bpy.data.objects.new(pid + "_lbl", txt)
    bpy.context.scene.collection.objects.link(to)
    to.location = (cx, 0, cz - CELL * 0.40)
    to.rotation_euler = (math.radians(90), 0, 0)
    m = bpy.data.materials.new("T")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.1, 0.12, 1)
    to.data.materials.append(m)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = int(280 * cols)
sc.render.resolution_y = int(300 * rows)
sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.80, 0.81, 0.84, 1)
for ang, e in (((math.radians(52), 0, math.radians(30)), 4.2),
               ((math.radians(100), 0, math.radians(-140)), 2.0)):
    L = bpy.data.lights.new("L", 'SUN')
    L.energy = e
    o = bpy.data.objects.new("L", L)
    sc.collection.objects.link(o)
    o.rotation_euler = ang

cam_d = bpy.data.cameras.new("C")
cam_d.type = 'ORTHO'
aspect = sc.render.resolution_y / sc.render.resolution_x
cam_d.ortho_scale = max(CELL * cols, CELL * rows / aspect)
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
# slight 3/4 tilt so parts read as solids, not flat cutouts
cam.location = (0, -8, 0)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print(f"[SHEET] {OUT}")
print("SHEET DONE")
