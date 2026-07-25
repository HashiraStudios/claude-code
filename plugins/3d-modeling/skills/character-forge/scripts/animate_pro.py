"""Professional animation pass (stage 6).

  blender --background --python animate_pro.py -- <painted.glb> <outdir> [clip]

Builds the rig (autorig.py), adds a REVERSE-FOOT IK setup, authors the
clip library, and writes MP4s plus a GLB with every action baked to plain
FK. Three rules here were each paid for with a rejected take:

1. FEET ROLL ABOUT GROUND PIVOTS, NEVER THE ANKLE. Rolling a foot around
   the ankle drives the heel through the floor. The rig chains
   Ground -> Heel -> Toe -> Ball -> Ankle with every pivot head sitting on
   the floor at a MEASURED contact point, so a roll rotates the foot about
   a point already on the ground and the sole cannot penetrate. In the air
   roll the ANKLE instead — a ground pivot mid-flight swings the ankle
   away from the hip and over-extends the chain.

2. POSE LIMBS ABOUT WORLD AXES, NEVER BONE-LOCAL EULER. Arm bones point
   down AND outward, so `rotation_euler.x` abducts them sideways instead
   of swinging them fore/aft; the same trap makes a Root bone that points
   up translate the character sideways when you key loc.z. Both shipped in
   earlier versions and neither is visible in a still frame. Everything
   here goes through wrot() / wloc().

3. THE PELVIS NEEDS HEADROOM. A generated character usually arrives with
   near-straight legs at rest, so any upward root motion silently
   over-extends the IK and the feet unstick. Every clip plays from a
   BASE_DIP crouch, in the air the feet rise WITH the body, and squash
   lives on the spine — scaling the Root scales the leg BONES and shrinks
   them off their planted targets.

Run check_anim.py afterwards: it measures floor penetration and IK reach
error per frame. Ship only at zero problems.
"""
import bpy, sys, math, os
from mathutils import Vector, Quaternion

_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC_IN = _argv[0]
BASE = _argv[1] if len(_argv) > 1 else "."
WHICH = _argv[2] if len(_argv) > 2 else "all"
os.makedirs(BASE, exist_ok=True)
_here = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(_here, "autorig.py")).read().split(
    chr(10) + 'if __name__ == "__main__":')[0])
SRC = SRC_IN

FPS, RES = 24, 640
STRIDE = 0.17          # half-stride: foot travel front->back during stance
LIFT = 0.075           # swing foot clearance
BASE_DIP = -0.022      # clips play from a slight crouch so the hips can RISE

# overlapping action: every bone lags its parent, so nothing moves as a block
LAG = {"Root": 0, "Hips": 0, "Spine": 1, "Chest": 2, "Head": 3, "Antenna": 6,
       "Clav.L": 2, "Clav.R": 2, "UpperArm.L": 3, "UpperArm.R": 3,
       "Forearm.L": 5, "Forearm.R": 5, "Hand.L": 6, "Hand.R": 6}
EASE = {"auto": ("BEZIER", "AUTO"), "smooth": ("SINE", "EASE_IN_OUT"),
        "out": ("SINE", "EASE_OUT"), "in": ("SINE", "EASE_IN"),
        "snap": ("QUAD", "EASE_IN"), "punch": ("BACK", "EASE_OUT"),
        "float": ("QUAD", "EASE_IN_OUT"), "linear": ("LINEAR", "AUTO")}

RIG = None      # set by build(); wrot/wloc need the rest matrices
SOLE = {}       # per side: measured heel / ball / toe / x


# --------------------------------------------------------------- measuring
def measure_soles(obj):
    """Find each foot's real contact points. A reverse foot is only exact
    if its pivots sit on the ACTUAL sole, so never assume them: take the
    vertices near the floor and read off the toe (front) and heel (back).
    The character faces -Y, so the toe is the -Y extreme."""
    out = {}
    for s, sgn in (("L", -1), ("R", 1)):
        sole = [v.co for v in obj.data.vertices
                if v.co.z < 0.02 and sgn * v.co.x > 0.02]
        if len(sole) < 20:
            raise RuntimeError(f"foot {s}: only {len(sole)} sole verts — is "
                               "the mesh normalised and standing on z=0?")
        toe_y, heel_y = min(p.y for p in sole), max(p.y for p in sole)
        out[s] = {"x": sum(p.x for p in sole) / len(sole),
                  "toe": toe_y, "heel": heel_y,
                  # the ball is where the foot flexes: ~2/3 toward the toe
                  "ball": heel_y + (toe_y - heel_y) * 0.68}
        print(f"[SOLE {s}] x={out[s]['x']:+.3f} heel={heel_y:+.3f} "
              f"ball={out[s]['ball']:+.3f} toe={toe_y:+.3f} n={len(sole)}")
    return out


def harden_soles(obj):
    """Make each sole RIGID to its own Foot bone.

    Heat skinning leaves the underside of the foot with some Shin
    influence, so the sole skews as the shin tilts through stance and a
    corner dips below the floor even though the IK target is exactly on the
    ground (measured -0.021 on the validation asset). Real foot skinning is
    rigid — a boot does not bend. Blended in over a band so no hard weight
    edge appears at the ankle.
    """
    hi, band, n = 0.075, 0.040, 0
    for v in obj.data.vertices:
        if v.co.z > hi or abs(v.co.x) < 0.03:
            continue
        s = "L" if v.co.x < 0 else "R"
        t = _smoothstep((hi - v.co.z) / band)
        if t <= 0.001:
            continue
        keep = 0.0
        for ge in list(v.groups):
            if obj.vertex_groups[ge.group].name == f"Foot.{s}":
                continue
            w = ge.weight * (1.0 - t)
            obj.vertex_groups[ge.group].add([v.index], w, 'REPLACE')
            keep += w
        obj.vertex_groups[f"Foot.{s}"].add([v.index], max(0.0, 1.0 - keep),
                                           'REPLACE')
        n += 1
    print(f"[SOLE] hardened {n} sole verts to their Foot bone")


# ------------------------------------------------------------ world posing
def wrot(bone, pitch=0.0, roll=0.0, yaw=0.0):
    """Author a rotation about WORLD axes; returns the bone's local XYZ
    euler in degrees. Bone-local euler is meaningless on a limb pointing
    diagonally — this is the only reliable way to say "swing it forward".

      pitch + : about world +X — a bone's +Z end tips FORWARD (-Y), so a
                DOWN-pointing limb swings BACKWARD.
      roll  + : about world +Y — lowers the +X side.
      yaw   + : about world +Z — carries the -X side forward.
    """
    Mi = RIG.data.bones[bone].matrix_local.to_3x3().inverted()
    q = Quaternion((1, 0, 0), 0)
    for axis, deg in ((Vector((1, 0, 0)), pitch), (Vector((0, 1, 0)), roll),
                      (Vector((0, 0, 1)), yaw)):
        if deg:
            q = Quaternion((Mi @ axis).normalized(), math.radians(deg)) @ q
    return [math.degrees(a) for a in q.to_euler('XYZ')]


def wloc(bone, y=0.0, z=0.0, x=0.0):
    """World-space offset -> that bone's local translation."""
    Mi = RIG.data.bones[bone].matrix_local.to_3x3().inverted()
    return Mi @ Vector((x, y, z))


# ------------------------------------------------------------ reverse foot
def add_ik(rig):
    """Reverse-foot rig: Ground -> Heel -> Toe -> Ball -> Ankle per side,
    with a 2-bone IK on each shin driven by the Ankle bone."""
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = rig.data.edit_bones
    g = ebs.new("Ground")
    g.head, g.tail = (0, 0, -0.05), (0, 0, 0.0)
    g.use_deform = False
    for s in "LR":
        m, parent = SOLE[s], g
        for tag in ("heel", "toe", "ball"):
            b = ebs.new(f"IK.{tag.capitalize()}.{s}")
            b.head, b.tail = (m["x"], m[tag], 0.0), (m["x"], m[tag] - 0.05, 0.0)
            b.roll, b.use_deform, b.parent = 0.0, False, parent
            b.use_connect = False
            parent = b
        # the IK chain ends at the SHIN, whose tail is the ANKLE, so the
        # target sits exactly there and MIRRORS the Foot bone (head, tail
        # AND roll) — any mismatch makes the copy-rotation twist the foot
        # into the floor even in the rest pose.
        a = ebs.new(f"IK.Ankle.{s}")
        a.head, a.tail = SK[f"Foot.{s}"][0], SK[f"Foot.{s}"][1]
        a.roll = ebs[f"Foot.{s}"].roll
        a.use_deform, a.parent, a.use_connect = False, parent, False
    bpy.ops.object.mode_set(mode='POSE')
    for s in "LR":
        c = rig.pose.bones[f"Shin.{s}"].constraints.new('IK')
        c.target, c.subtarget, c.chain_count = rig, f"IK.Ankle.{s}", 2
        cc = rig.pose.bones[f"Foot.{s}"].constraints.new('COPY_ROTATION')
        cc.target, cc.subtarget, cc.influence = rig, f"IK.Ankle.{s}", 1.0
    bpy.ops.object.mode_set(mode='OBJECT')


class Clip:
    def __init__(self, name, length, cyclic=True):
        self.name, self.length, self.cyclic = name, length, cyclic
        self.keys = []

    def bone(self, name, frame, rot=None, loc=None, scale=None, ease="auto"):
        self.keys.append((name, frame, rot, loc, scale, ease))

    def apply(self, rig):
        act = bpy.data.actions.new(self.name)
        rig.animation_data_create()
        rig.animation_data.action = act
        # a seamless loop needs real NEIGHBOURS outside the range, not just
        # matching end poses: emit every key one period before and after so
        # the interpolator's tangents wrap instead of flattening.
        reps = (-1, 0, 1) if self.cyclic else (0,)
        for name, frame, rot, loc, scale, ease in self.keys:
            if name not in rig.pose.bones:
                continue
            pb = rig.pose.bones[name]
            pb.rotation_mode = 'XYZ'
            for r in reps:
                f = frame + LAG.get(name, 0) + r * self.length
                if rot is not None:
                    pb.rotation_euler = tuple(math.radians(a) for a in rot)
                    pb.keyframe_insert('rotation_euler', frame=f)
                if loc is not None:
                    pb.location = loc
                    pb.keyframe_insert('location', frame=f)
                if scale is not None:
                    pb.scale = scale
                    pb.keyframe_insert('scale', frame=f)
                for fc in act.fcurves:
                    if f'"{name}"' not in fc.data_path:
                        continue
                    for kp in fc.keyframe_points:
                        if abs(kp.co.x - f) < 1e-4:
                            kp.interpolation, kp.easing = EASE[ease]
                            kp.handle_left_type = 'AUTO_CLAMPED'
                            kp.handle_right_type = 'AUTO_CLAMPED'
        return act


# ------------------------------------------------------------- pose helpers
def foot(c, s, frame, y=0.0, z=0.0, toe_up=0.0, heel_up=0.0, point=0.0,
         ease="auto"):
    """Place a foot in world terms and rock it about the right pivot.

    toe_up  rotates about the HEEL contact  (heel strike)   — grounded
    heel_up rotates about the TOE contact   (toe-off)       — grounded
    point   rotates about the ANKLE itself  (toes pointed)  — airborne
    """
    c.bone(f"IK.Heel.{s}", frame, loc=wloc(f"IK.Heel.{s}", y, z),
           rot=wrot(f"IK.Heel.{s}", pitch=-toe_up), ease=ease)
    c.bone(f"IK.Toe.{s}", frame, rot=wrot(f"IK.Toe.{s}", pitch=heel_up),
           ease=ease)
    c.bone(f"IK.Ankle.{s}", frame, rot=wrot(f"IK.Ankle.{s}", pitch=point),
           ease=ease)


def root(c, f, z=0.0, x=0.0, ease="auto"):
    """Root translation in WORLD terms; z is measured from BASE_DIP.
    Must go through wloc: the Root bone points along +Z, so its local Y
    axis IS world Z, and keying loc=(x, 0, z) slides the character sideways
    and backwards instead of bobbing it."""
    c.bone("Root", f, loc=wloc("Root", y=0.0, z=BASE_DIP + z, x=x), ease=ease)


def squash(c, f, sq, ease="auto"):
    """Squash & stretch on the SPINE, never the Root: root scale scales the
    leg bones too and shrinks them off their planted IK targets."""
    c.bone("Spine", f, scale=(1.0 / math.sqrt(sq), 1.0 / math.sqrt(sq), sq),
           ease=ease)


def upper_body(c, f, lean, twist, tilt, ease):
    """Spine chain from three world-space numbers. The chest counter-twists
    the pelvis and the head counter-twists the chest, which is what keeps a
    walk from looking like a rotating statue."""
    c.bone("Hips", f, rot=wrot("Hips", roll=tilt, yaw=twist), ease=ease)
    c.bone("Spine", f, rot=wrot("Spine", pitch=lean * 0.5, roll=tilt * 0.3,
                                yaw=-twist * 0.35), ease="smooth")
    c.bone("Chest", f, rot=wrot("Chest", pitch=lean * 0.4, roll=tilt * 0.2,
                                yaw=-twist * 0.7), ease="smooth")
    c.bone("Head", f, rot=wrot("Head", pitch=-lean * 0.6, roll=-tilt * 0.4,
                               yaw=twist * 0.5), ease="smooth")
    if "Antenna" in RIG.pose.bones:
        c.bone("Antenna", f, rot=wrot("Antenna", pitch=lean * 1.8, roll=-tilt),
               ease="smooth")


def arms(c, f, swing_L, swing_R, bend=14, ease="smooth"):
    """swing_* is degrees FORWARD (a down-pointing limb swings forward on
    NEGATIVE world pitch — see wrot)."""
    for s, sw in (("L", swing_L), ("R", swing_R)):
        c.bone(f"UpperArm.{s}", f, rot=wrot(f"UpperArm.{s}", pitch=-sw),
               ease=ease)
        c.bone(f"Forearm.{s}", f,
               rot=wrot(f"Forearm.{s}", pitch=-(bend + max(0.0, sw) * 0.5)),
               ease=ease)


# ------------------------------------------------------------------- clips
def clip_walk():
    """32f treadmill cycle, 56% stance. The stance foot is welded to the
    floor and slides backward at stride speed, so contact never slips; the
    swing foot arcs forward. Knees bend as a RESULT of the IK."""
    c = Clip("Walk", 32)
    # (phase, y, z, toe_up, heel_up, ease) — y+ is behind the body
    traj = [(0,  -STRIDE,        0.0,   14, 0,  "linear"),  # heel strike
            (3,  -STRIDE * 0.70, 0.0,   0,  0,  "out"),     # foot flat
            (9,   0.0,           0.0,   0,  0,  "linear"),  # midstance
            (14,  STRIDE * 0.70, 0.0,   0,  13, "in"),      # heel peels up
            (18,  STRIDE,        0.0,   0,  32, "out"),     # toe off
            (21,  STRIDE * 0.25, LIFT * 0.8, 0, 18, "smooth"),
            (25, -STRIDE * 0.35, LIFT,  0,  0,  "smooth"),  # passing
            (29, -STRIDE * 0.85, LIFT * 0.35, 9, 0, "in")]  # reaching out
    for s, phase in (("L", 0), ("R", 16)):
        for pf, y, z, tu, hu, ease in traj:
            foot(c, s, 1 + ((pf + phase) % 32), y=y, z=z, toe_up=tu,
                 heel_up=hu, ease=ease)
    # The contact frames are the LOWEST: the stance foot reaches far
    # forward there, so a pelvis that rises instead over-extends the chain.
    # (frame, root z, root x, pelvis yaw, pelvis tilt, lean, ease)
    body = [(1,  -0.008, 0.000,  6,  3, 3.0, "snap"),   # L contact
            (5,   0.000, -0.014, 4,  4, 3.5, "out"),
            (9,   0.020, -0.018, 0,  2, 2.5, "in"),     # L midstance
            (13,  0.010, -0.008, -4, -1, 3.0, "auto"),
            (17, -0.008, 0.000, -6, -3, 3.0, "snap"),   # R contact
            (21,  0.000, 0.014, -4, -4, 3.5, "out"),
            (25,  0.020, 0.018,  0, -2, 2.5, "in"),     # R midstance
            (29,  0.010, 0.008,  4,  1, 3.0, "auto")]
    for f, bz, bx, twist, tilt, lean, ease in body:
        root(c, f, bz, bx, ease)
        upper_body(c, f, lean, twist, tilt, ease)
        # arms oppose the legs: at f1 the -X foot is forward, so the +X arm
        # leads. LAG makes the forearms trail into follow-through.
        sw = 17 * math.cos(math.radians((f - 1) / 32 * 360))
        arms(c, f, swing_L=-sw, swing_R=sw)
    return c, 32


def clip_hop():
    """60f hop: anticipation crouch, explosive extension, tuck, reach,
    absorb. The feet stay welded through the crouch and rise WITH the body
    in the air — otherwise the IK over-extends and the legs detach."""
    c = Clip("Hop", 60, cyclic=False)
    # (frame, root z, squash, foot z, tuck y, heel_up, point, lean, ease)
    # heel_up only while grounded, point only while airborne.
    K = [(1,   0.000, 1.00, 0.000,  0.000, 0,  0,  0,  "in"),
         (9,  -0.045, 0.96, 0.000,  0.000, 0,  0,  16, "out"),   # crouch
         (15, -0.075, 0.93, 0.000,  0.000, 0,  0,  22, "smooth"),  # deepest
         (18, -0.055, 0.95, 0.000,  0.000, 5,  0,  20, "snap"),  # heels peel
         (21,  0.020, 1.07, 0.000,  0.000, 26, 0, -14, "punch"),  # toe-off
         (25,  0.120, 1.05, 0.155, -0.060, 0,  30, -10, "float"),  # tuck
         (31,  0.170, 1.03, 0.205, -0.075, 0,  26, -6,  "float"),  # apex
         (37,  0.110, 1.02, 0.150, -0.045, 0,  20,  2,  "in"),
         (42,  0.020, 1.01, 0.028, -0.008, 0,  14, 10,  "in"),   # reach down
         (45, -0.040, 0.94, 0.000,  0.000, 8,  0,  18, "punch"),  # toes first
         (48, -0.030, 0.97, 0.000,  0.000, 0,  0,  14, "out"),   # heel drops
         (52, -0.010, 1.03, 0.000,  0.000, 0,  0,  6,  "out"),   # rebound
         (56,  0.004, 0.99, 0.000,  0.000, 0,  0,  2,  "smooth"),
         (60,  0.000, 1.00, 0.000,  0.000, 0,  0,  0,  "smooth")]
    for f, bz, sq, fz, ty, hu, pt, lean, ease in K:
        root(c, f, bz, ease=ease)
        squash(c, f, sq, ease)
        for s in "LR":
            foot(c, s, f, y=ty, z=fz, heel_up=hu, point=pt, ease=ease)
        upper_body(c, f, lean, 0, 0, ease)
        # arms wind up on the crouch and throw up through the launch
        sw = -lean * 2.4
        arms(c, f, swing_L=sw, swing_R=sw, bend=14 + abs(lean) * 0.6, ease=ease)
    return c, 60


def clip_idle():
    """72f breathing loop: weight shifts foot to foot, feet planted, and a
    MOVING HOLD (the pose keeps drifting) so it never freezes."""
    c = Clip("Idle", 72)
    # (frame, root z, root x, tilt, breathe, twist)
    K = [(1,   0.008, 0.000,  0,   0,   0),
         (18, -0.004, -0.012, 2.4, 2.2, 2.0),
         (36,  0.010, 0.000,  0,   0.4, 0),
         (54, -0.004, 0.012, -2.4, 2.2, -2.0),
         (72,  0.008, 0.000,  0,   0,   0)]
    for f, bz, bx, tilt, breathe, twist in K:
        root(c, f, bz, bx, "smooth")
        upper_body(c, f, breathe, twist, tilt, "smooth")
        arms(c, f, swing_L=-twist * 1.6, swing_R=twist * 1.6,
             bend=14 + abs(twist))
        for s in "LR":
            foot(c, s, f, ease="smooth")
    return c, 72


def clip_turntable():
    c = Clip("Turntable", 96, cyclic=False)
    for f, deg in ((1, 0), (96, 360)):
        c.bone("Root", f, loc=wloc("Root", z=BASE_DIP),
               rot=wrot("Root", yaw=deg), ease="linear")
        for s in "LR":
            # the feet ride the turntable with the body
            c.bone(f"IK.Heel.{s}", f, rot=wrot(f"IK.Heel.{s}", yaw=deg),
                   ease="linear")
    return c, 96


CLIPS = {"idle": clip_idle, "walk": clip_walk, "hop": clip_hop,
         "turntable": clip_turntable}


# ------------------------------------------------------------------- stage
def setup_stage(res=RES):
    """Render rig WITH a ground plane and real shadows — without a floor
    there is no way to judge contact and every clip reads as floating."""
    scene, cam = setup_render(res)
    scene.render.fps = FPS
    scene.eevee.use_soft_shadows = True
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    m = bpy.data.materials.new("Floor")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.80, 0.80, 0.78, 1)
    bsdf.inputs["Roughness"].default_value = 0.95
    floor.data.materials.append(m)
    for lt in [o for o in bpy.data.objects if o.type == 'LIGHT']:
        lt.data.use_shadow = True
        if lt.data.type == 'SUN':
            lt.data.angle = math.radians(6)
    center = Vector((0, 0, 0.52))
    d = Vector((-0.62, -1.0, 0.30)).normalized()
    cam.location = center + d * 2.25
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    return scene, cam


def render_mp4(scene, path, f0, f1):
    """Blender encodes H.264 itself — no system ffmpeg needed. Never GIF."""
    scene.frame_start, scene.frame_end = f0, f1
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.filepath = path
    bpy.ops.render.render(animation=True)
    real = path if os.path.exists(path) else f"{path}{f0:04d}-{f1:04d}.mp4"
    print(f"[MP4] {real} {os.path.getsize(real) if os.path.exists(real) else 0}")


def build():
    """Mesh + rig + reverse-foot IK. Shared with check_anim.py so what gets
    validated is exactly what gets rendered."""
    global RIG, SOLE
    obj = load_and_normalize(SRC)
    rig = build_armature()
    bind(obj, rig)
    mask_weights(obj, rig, " pre")
    polish_weights(obj)
    mask_weights(obj, rig, " post")
    harden_soles(obj)
    SOLE = measure_soles(obj)
    add_ik(rig)
    RIG = rig
    return obj, rig


if __name__ == "__main__":
    obj, rig = build()
    scene, cam = setup_stage()
    bpy.context.view_layer.objects.active = rig

    for name in (list(CLIPS) if WHICH == "all" else [WHICH]):
        clip, length = CLIPS[name]()
        clip.apply(rig)
        render_mp4(scene, os.path.join(BASE, f"{name}.mp4"), 1, length)
        print(f"CLIP {name} ({length}f) done")

    # bake IK -> FK so the exported GLB carries plain bone curves that any
    # engine can play without an IK solver
    for name in CLIPS:
        clip, length = CLIPS[name]()
        clip.apply(rig)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.pose.select_all(action='SELECT')
        bpy.ops.nla.bake(frame_start=1, frame_end=length, only_selected=False,
                         visual_keying=True, clear_constraints=False,
                         use_current_action=True, bake_types={'POSE'})
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"[BAKE] {name}")
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        for con in list(pb.constraints):
            pb.constraints.remove(con)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=os.path.join(BASE, "animated.glb"),
                              use_selection=True, export_animations=True,
                              export_animation_mode='ACTIONS')
    print("ANIMATE DONE")
