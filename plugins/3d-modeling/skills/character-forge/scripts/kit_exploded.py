"""Exploded assembly diagram from a placement manifest.

  blender -b --python kit_exploded.py -- <parts_dir> <placement.json> <out.png>

The kit is assembled by a person, so the deliverable has to say WHERE
each piece goes. This renders every part pushed outward along its
mounting direction with a leader line back to its seat on the body, and
labels it — the diagram that turns a folder of meshes into instructions.

placement.json:
  {"host": "body",
   "scale_ref": 1.0,
   "items": [{"part": "wheel", "label": "Wheel FL", "pos": [-0.42,-0.55,0.22],
              "scale": 0.30, "rot": [0,0,0], "explode": [-0.5,0,0]}, ...]}

`pos` is where the part actually sits (host normalised to height 1.0),
`explode` is the direction it is pulled apart for the diagram. Keeping
them separate means the same manifest drives BOTH the picture and a real
assembly, and nobody has to reverse-engineer true positions from an
exploded render.
"""
import bpy, sys, os, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
PARTS_DIR, PLACEMENT, OUT = argv[0], argv[1], argv[2]
plc = json.load(open(PLACEMENT))

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)


def load(part_id):
    before = set(bpy.data.objects)
    path = os.path.join(PARTS_DIR, part_id + ".glb")
    if not os.path.exists(path):
        print(f"[MISS] {part_id}")
        return None
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if not new:
        return None
    obj = max(new, key=lambda o: len(o.data.polygons))
    for o in new:
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bb = [Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    # normalise every part to unit height first, so manifest scales are
    # readable numbers instead of whatever the generator happened to emit
    s = 1.0 / max((hi - lo).z, 1e-6)
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    return obj


def place(obj, pos, scale, rot, explode):
    obj.scale = tuple(v * scale for v in obj.scale)
    obj.rotation_euler = tuple(math.radians(a) for a in rot)
    obj.location = Vector(pos) + Vector(explode)
    return Vector(pos), Vector(pos) + Vector(explode)


lines = []
host = load(plc["host"])
if host:
    place(host, (0, 0, 0), plc.get("scale_ref", 1.0), (0, 0, 0), (0, 0, 0))

for it in plc["items"]:
    o = load(it["part"])
    if not o:
        continue
    o.name = it.get("label", it["part"])
    seat, shown = place(o, it["pos"], it.get("scale", 1.0),
                        it.get("rot", [0, 0, 0]), it.get("explode", [0, 0, 0]))
    if (shown - seat).length > 1e-4:
        lines.append((seat, shown, it.get("label", it["part"])))

# leader lines: thin cylinders from the seat to the exploded position
for seat, shown, label in lines:
    d = shown - seat
    bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=d.length,
                                        location=tuple((seat + shown) / 2))
    c = bpy.context.active_object
    c.rotation_mode = 'QUATERNION'
    c.rotation_quaternion = d.to_track_quat('Z', 'Y')
    m = bpy.data.materials.new("L")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.15, 0.15, 0.18, 1)
    c.data.materials.append(m)
    t = bpy.data.curves.new(label, 'FONT')
    t.body = label
    t.size = 0.05
    t.align_x = 'CENTER'
    to = bpy.data.objects.new(label + "_l", t)
    bpy.context.scene.collection.objects.link(to)
    to.location = shown + d.normalized() * 0.10
    to.rotation_euler = (math.radians(90), 0, 0)
    tm = bpy.data.materials.new("TL")
    tm.use_nodes = True
    tm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.08, 0.1, 1)
    to.data.materials.append(tm)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 1500, 1000
sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.94, 0.94, 0.96, 1)
for ang, e in (((math.radians(56), 0, math.radians(38)), 3.0),
               ((math.radians(70), 0, math.radians(-130)), 1.3)):
    L = bpy.data.lights.new("L", 'SUN')
    L.energy = e
    lo_ = bpy.data.objects.new("L", L)
    sc.collection.objects.link(lo_)
    lo_.rotation_euler = ang

cam_d = bpy.data.cameras.new("C")
cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam_d.lens = 55
center = Vector(plc.get("look_at", (0, 0, 0.25)))
cam.location = center + Vector((-1.6, -2.4, 1.3))
cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print(f"[EXPLODED] {OUT}")
print("EXPLODED DONE")
