"""Rig stage: spatial vertex groups + armature (ARMATURE_NAME skinning),
weight verify + smooth, neutral & pose renders, final GLB export.

  blender --background --python rig_character.py -- <painted.glb> <final.glb> biped_chibi

Configs are normalized to the mesh frame (height 1.0, feet z=0,
front = -Y). Tune the boxes to the character's proportions if the
default grab is wrong — verify with the pose render (no tears)."""
import bpy, sys, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, CONFIG = argv[0], argv[1], argv[2] if len(argv) > 2 else "biped_chibi"

CONFIGS = {
    # dragon-like: big head, stubby limbs, tail
    "biped_chibi": dict(
        groups=lambda x, y, z: (
            'Head' if (z > 0.55 or (y < -0.25 and z > 0.45)) else
            ('Arm.L' if x < 0 else 'Arm.R') if (abs(x) > 0.21 and 0.18 < z < 0.50 and -0.25 < y < 0.12) else
            'Tail' if (y > 0.28 and z < 0.55) else
            ('Leg.L' if x < 0 else 'Leg.R') if (z < 0.25 and abs(x) > 0.04 and y < 0.24) else
            'Body'),
        bones=[('Body', (0, 0.02, 0.12), (0, 0.02, 0.52), None),
               ('Head', (0, 0.02, 0.52), (0, -0.05, 0.92), 'Body'),
               ('Arm.L', (-0.19, -0.03, 0.44), (-0.27, -0.07, 0.22), 'Body'),
               ('Arm.R', (0.19, -0.03, 0.44), (0.27, -0.07, 0.22), 'Body'),
               ('Leg.L', (-0.12, 0.0, 0.22), (-0.12, -0.03, 0.02), 'Body'),
               ('Leg.R', (0.12, 0.0, 0.22), (0.12, -0.03, 0.02), 'Body'),
               ('Tail', (0, 0.18, 0.18), (0, 0.45, 0.25), 'Body')],
        smooth=dict(factor=0.5, repeat=2, expand=0.15),
        pose=[('Head', dict(x=-6, z=12)), ('Arm.L', dict(x=-30)),
              ('Arm.R', dict(x=16)), ('Tail', dict(z=14))]),
    # mecha: rigid parts, wide arms, no tail
    "biped_mecha": dict(
        groups=lambda x, y, z: (
            ('Arm.L' if x < 0 else 'Arm.R') if (abs(x) > 0.26 and 0.15 < z < 0.72) else
            ('Leg.L' if x < 0 else 'Leg.R') if (z < 0.30 and 0.05 < abs(x) < 0.26) else
            'Body'),
        bones=[('Body', (0, 0, 0.15), (0, 0, 0.78), None),
               ('Arm.L', (-0.30, 0.0, 0.62), (-0.40, -0.04, 0.28), 'Body'),
               ('Arm.R', (0.30, 0.0, 0.62), (0.40, -0.04, 0.28), 'Body'),
               ('Leg.L', (-0.15, 0.0, 0.28), (-0.15, -0.03, 0.02), 'Body'),
               ('Leg.R', (0.15, 0.0, 0.28), (0.15, -0.03, 0.02), 'Body')],
        smooth=dict(factor=0.4, repeat=1, expand=0.1),
        pose=[('Body', dict(z=8)), ('Arm.L', dict(x=-30)),
              ('Arm.R', dict(x=22)), ('Leg.L', dict(x=-8)), ('Leg.R', dict(x=8))]),
}

cfg = CONFIGS[CONFIG]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
char = max(meshes, key=lambda o: len(o.data.polygons))
for o in meshes:
    if o is not char:
        bpy.data.objects.remove(o, do_unlink=True)
char.name = "Character"
bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
bpy.context.view_layer.objects.active = char
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
# normalize
bpy.context.view_layer.update()
bb = [char.matrix_world @ Vector(c) for c in char.bound_box]
lo = Vector((min(v[i] for v in bb) for i in range(3)))
hi = Vector((max(v[i] for v in bb) for i in range(3)))
s = 1.0 / (hi.z - lo.z)
char.scale = (s, s, s)
bpy.context.view_layer.update()
bb = [char.matrix_world @ Vector(c) for c in char.bound_box]
lo = Vector((min(v[i] for v in bb) for i in range(3)))
hi = Vector((max(v[i] for v in bb) for i in range(3)))
char.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

bone_names = [b[0] for b in cfg["bones"]]
char.vertex_groups.clear()
vgs = {n: char.vertex_groups.new(name=n) for n in bone_names}
for v in char.data.vertices:
    g = cfg["groups"](*v.co)
    vgs[g].add([v.index], 1.0, 'REPLACE')

bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
rig = bpy.context.active_object
rig.name = "Rig"
ebs = rig.data.edit_bones
root_name, rh, rt, _ = cfg["bones"][0]
ebs[0].name = root_name
ebs[0].head, ebs[0].tail = rh, rt
for name, h, t, parent in cfg["bones"][1:]:
    b = ebs.new(name)
    b.head, b.tail, b.parent = h, t, ebs[parent]
bpy.ops.object.mode_set(mode='OBJECT')

for o in bpy.data.objects:
    o.select_set(False)
char.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type='ARMATURE_NAME')
empty = [v for v in char.data.vertices
         if not v.groups or all(g.weight < 1e-4 for g in v.groups)]
print(f"[WEIGHTS] empty={len(empty)}/{len(char.data.vertices)}")
assert not empty, "empty-weight vertices — adjust the group boxes"
try:
    bpy.context.view_layer.objects.active = char
    bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
    bpy.ops.object.vertex_group_smooth(group_select_mode='ALL', **cfg["smooth"])
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    print("[WEIGHTS] smoothed")
except Exception as e:
    print("[WEIGHTS] smooth skipped:", e)

# pose test render (EEVEE, quick)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 1024
world = bpy.data.worlds.new("W"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.92, 0.9, 1)
scene.world = world
key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", 'SUN'))
key.data.energy = 3.0
key.rotation_euler = (math.radians(50), 0, math.radians(-35))
bpy.context.collection.objects.link(key)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
bpy.context.collection.objects.link(cam)
scene.camera = cam
center = Vector((0, 0, 0.5))
d = Vector((-0.75, -1.0, 0.45)).normalized()
cam.location = center + d * 1.9
cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()

bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE')
for name, rots in cfg["pose"]:
    pb = rig.pose.bones[name]
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = (math.radians(rots.get('x', 0)),
                         math.radians(rots.get('y', 0)),
                         math.radians(rots.get('z', 0)))
bpy.ops.object.mode_set(mode='OBJECT')
scene.render.filepath = OUT.rsplit('.', 1)[0] + "_posetest.png"
bpy.ops.render.render(write_still=True)
print(f"[POSE TEST] {scene.render.filepath} — check for tears")

bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE')
for pb in rig.pose.bones:
    pb.rotation_euler = (0, 0, 0)
bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
rig.select_set(True)
bpy.ops.export_scene.gltf(filepath=OUT, use_selection=True)
print(f"RIG DONE -> {OUT}")
