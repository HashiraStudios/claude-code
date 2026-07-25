"""Stage 4 — rig + animation clips + MP4 renders + animated GLB export.

  blender --background --python animate_character.py -- <painted.glb> <outdir> [rig] [clips]
    rig   : biped_mecha (default) | biped_chibi
    clips : all (default) | comma list of idle,walk,hop,turntable

Outputs <outdir>/<clip>.mp4 (H.264 via Blender's built-in encoder — no
system ffmpeg needed) plus <outdir>/animated.glb carrying every action,
ready for Three.js / Unity / Unreal / Godot.

Rig notes: a Root bone (feet-anchored, unweighted) parents Body and the
legs. Root translation = hop/bob; Root z-scale = squash & stretch about
the ground; legs hang off Root so a Body rotation does not drag them.
Keep summed lateral bends under ~20° on thin appendages (fins, tails)
or the shell shears.
"""
import bpy, sys, math, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC = argv[0]
OUTDIR = argv[1]
RIG = argv[2] if len(argv) > 2 else "biped_mecha"
WANT = (argv[3] if len(argv) > 3 else "all").split(",")
RES, FPS = 640, 24
os.makedirs(OUTDIR, exist_ok=True)

RIGS = {
    "biped_mecha": dict(
        groups=lambda x, y, z: (
            ('Arm.L' if x < 0 else 'Arm.R') if (abs(x) > 0.26 and 0.15 < z < 0.72) else
            ('Leg.L' if x < 0 else 'Leg.R') if (z < 0.30 and 0.05 < abs(x) < 0.26) else
            'Body'),
        bones=[('Root', (0, 0, 0.0), (0, 0, 0.14), None),
               ('Body', (0, 0, 0.15), (0, 0, 0.78), 'Root'),
               ('Arm.L', (-0.30, 0.0, 0.62), (-0.40, -0.04, 0.28), 'Body'),
               ('Arm.R', (0.30, 0.0, 0.62), (0.40, -0.04, 0.28), 'Body'),
               ('Leg.L', (-0.15, 0.0, 0.28), (-0.15, -0.03, 0.02), 'Root'),
               ('Leg.R', (0.15, 0.0, 0.28), (0.15, -0.03, 0.02), 'Root')],
        smooth=dict(factor=0.4, repeat=1, expand=0.1)),
    "biped_chibi": dict(
        groups=lambda x, y, z: (
            'Head' if (z > 0.55 or (y < -0.25 and z > 0.45)) else
            ('Arm.L' if x < 0 else 'Arm.R') if (abs(x) > 0.21 and 0.18 < z < 0.50 and -0.25 < y < 0.12) else
            'Tail' if (y > 0.28 and z < 0.55) else
            ('Leg.L' if x < 0 else 'Leg.R') if (z < 0.25 and abs(x) > 0.04 and y < 0.24) else
            'Body'),
        bones=[('Root', (0, 0, 0.0), (0, 0, 0.11), None),
               ('Body', (0, 0.02, 0.12), (0, 0.02, 0.52), 'Root'),
               ('Head', (0, 0.02, 0.52), (0, -0.05, 0.92), 'Body'),
               ('Arm.L', (-0.19, -0.03, 0.44), (-0.27, -0.07, 0.22), 'Body'),
               ('Arm.R', (0.19, -0.03, 0.44), (0.27, -0.07, 0.22), 'Body'),
               ('Leg.L', (-0.12, 0.0, 0.22), (-0.12, -0.03, 0.02), 'Root'),
               ('Leg.R', (0.12, 0.0, 0.22), (0.12, -0.03, 0.02), 'Root'),
               ('Tail', (0, 0.18, 0.18), (0, 0.45, 0.25), 'Body')],
        smooth=dict(factor=0.5, repeat=2, expand=0.15)),
}
cfg = RIGS[RIG]
HAS = {b[0] for b in cfg["bones"]}

# ------------------------------------------------------------ load + norm
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
for p in char.data.polygons:
    p.use_smooth = True
if hasattr(char.data, "use_auto_smooth"):
    char.data.use_auto_smooth = True
    char.data.auto_smooth_angle = math.radians(42)

# ------------------------------------------------------------ rig
char.vertex_groups.clear()
vgs = {n: char.vertex_groups.new(name=n) for n in HAS}
for v in char.data.vertices:
    vgs[cfg["groups"](*v.co)].add([v.index], 1.0, 'REPLACE')

bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
rig = bpy.context.active_object
rig.name = "Rig"
ebs = rig.data.edit_bones
root = cfg["bones"][0]
ebs[0].name = root[0]
ebs[0].head, ebs[0].tail = root[1], root[2]
for name, h, t, parent in cfg["bones"][1:]:
    b = ebs.new(name)
    b.head, b.tail, b.parent = h, t, ebs[parent]
    b.use_connect = False
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
assert not empty, "empty-weight vertices — adjust the rig group boxes"
bpy.context.view_layer.objects.active = char
bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
bpy.ops.object.vertex_group_smooth(group_select_mode='ALL', **cfg["smooth"])
bpy.ops.object.vertex_group_normalize_all(lock_active=False)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.objects.active = rig

# ------------------------------------------------------------ anim utils
scene = bpy.context.scene
scene.render.fps = FPS

def key(bone, frame, rot=None, loc=None, scale=None):
    if bone not in HAS:
        return
    pb = rig.pose.bones[bone]
    pb.rotation_mode = 'XYZ'
    if rot:
        pb.rotation_euler = tuple(math.radians(a) for a in rot)
        pb.keyframe_insert('rotation_euler', frame=frame)
    if loc:
        pb.location = loc
        pb.keyframe_insert('location', frame=frame)
    if scale:
        pb.scale = scale
        pb.keyframe_insert('scale', frame=frame)

def new_action(name):
    act = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = act
    return act

def ease(act, mode='BEZIER'):
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = mode
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'

def build_idle():
    act = new_action("Idle")
    for f, (bz, brx, brz, aL, aR) in {
            1: (0.0, 0, 0, 0, 0), 12: (0.018, -2, 2, -7, 5),
            24: (0.0, 0, 0, 0, 0), 36: (0.018, 2, -2, 5, -7),
            48: (0.0, 0, 0, 0, 0)}.items():
        key('Root', f, loc=(0, 0, bz))
        key('Body', f, rot=(brx, 0, brz))
        key('Head', f, rot=(-brx * 0.6, 0, brz * 0.5))
        key('Arm.L', f, rot=(aL, 0, 0))
        key('Arm.R', f, rot=(aR, 0, 0))
        key('Leg.L', f, rot=(0, 0, 0))
        key('Leg.R', f, rot=(0, 0, 0))
        key('Tail', f, rot=(0, 0, brz * 3))
    ease(act)
    return act, 1, 48

def build_walk():
    act = new_action("Walk")
    F = {1:  (22, -22, -16, 16, 0.010, -3), 5:  (14, -14, -10, 10, -0.010, -4),
         9:  (0, 0, 0, 0, 0.014, 0),        13: (-14, 14, 10, -10, -0.006, 3),
         17: (-22, 22, 16, -16, 0.010, 4),  21: (-14, 14, 10, -10, -0.010, 3),
         25: (0, 0, 0, 0, 0.014, 0),        29: (14, -14, -10, 10, -0.006, -3),
         33: (22, -22, -16, 16, 0.010, -3)}
    for f, (lL, lR, aL, aR, bz, roll) in F.items():
        key('Root', f, loc=(0, 0, bz))
        key('Body', f, rot=(0, roll, 0))
        key('Head', f, rot=(0, -roll * 0.5, 0))
        key('Leg.L', f, rot=(lL, 0, 0))
        key('Leg.R', f, rot=(lR, 0, 0))
        key('Arm.L', f, rot=(aL, 0, 0))
        key('Arm.R', f, rot=(aR, 0, 0))
        key('Tail', f, rot=(0, 0, roll * 2))
    ease(act)
    return act, 1, 32

def build_hop():
    act = new_action("Hop")
    F = {1:  (0.0, 1.00, 0, 0, 0),      8:  (-0.055, 0.92, 10, -16, -24),
         12: (-0.070, 0.88, 14, -22, -34), 16: (0.090, 1.10, -12, 26, 44),
         22: (0.230, 1.05, -6, 18, 52),  28: (0.090, 1.02, 4, -6, 30),
         32: (-0.050, 0.90, 12, -20, -10), 37: (0.012, 1.04, -4, 6, 6),
         44: (0.0, 1.00, 0, 0, 0)}
    for f, (z, sq, body, legs, arms) in F.items():
        key('Root', f, loc=(0, 0, z), scale=(1, 1, sq))
        key('Body', f, rot=(body, 0, 0))
        key('Head', f, rot=(-body * 0.5, 0, 0))
        key('Leg.L', f, rot=(legs, 0, 0))
        key('Leg.R', f, rot=(legs, 0, 0))
        key('Arm.L', f, rot=(arms, 0, 0))
        key('Arm.R', f, rot=(arms, 0, 0))
        key('Tail', f, rot=(-body * 0.8, 0, 0))
    ease(act)
    return act, 1, 44

def build_turntable():
    act = new_action("TT")
    for f, deg in ((1, 0), (48, 360)):
        key('Root', f, rot=(0, 0, deg))
    for fc in act.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    return act, 1, 48

CLIPS = {"idle": build_idle, "walk": build_walk, "hop": build_hop,
         "turntable": build_turntable}

# ------------------------------------------------------------ render rig
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = RES
scene.eevee.taa_render_samples = 16
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.92, 0.90, 1)
scene.world = world
kl = bpy.data.objects.new("Key", bpy.data.lights.new("Key", 'SUN'))
kl.data.energy = 3.2
kl.rotation_euler = (math.radians(52), 0, math.radians(-38))
bpy.context.collection.objects.link(kl)
fl = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", 'SUN'))
fl.data.energy = 1.1
fl.rotation_euler = (math.radians(65), 0, math.radians(140))
bpy.context.collection.objects.link(fl)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
bpy.context.collection.objects.link(cam)
scene.camera = cam
center = Vector((0, 0, 0.55))
d = Vector((-0.72, -1.0, 0.34)).normalized()
cam.location = center + d * 2.1
cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()

def render_mp4(path, f_start, f_end):
    scene.frame_start, scene.frame_end = f_start, f_end
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.filepath = path
    bpy.ops.render.render(animation=True)
    real = path if os.path.exists(path) else f"{path}{f_start:04d}-{f_end:04d}.mp4"
    print(f"[MP4] {real} ({os.path.getsize(real) if os.path.exists(real) else 0} bytes)")

todo = list(CLIPS) if WANT == ["all"] else [c for c in WANT if c in CLIPS]
for name in todo:
    act, fs, fe = CLIPS[name]()
    render_mp4(os.path.join(OUTDIR, f"{name}.mp4"), fs, fe)
    print(f"CLIP {name} done")

for name in CLIPS:            # make sure every action exists in the file
    if name not in todo:
        CLIPS[name]()
bpy.ops.object.select_all(action='DESELECT')
char.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=os.path.join(OUTDIR, "animated.glb"),
                          use_selection=True, export_animations=True,
                          export_animation_mode='ACTIONS')
print(f"ANIMATE DONE -> {OUTDIR}/animated.glb")
