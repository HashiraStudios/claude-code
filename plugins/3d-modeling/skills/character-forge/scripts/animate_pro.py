"""Professional animation pass (stage 4).

  blender --background --python animate_pro.py -- <painted.glb> <outdir> [clip]

Builds the pro rig (autorig.py) then authors the clip library.

Fixes the "stiff, nota 2" problems explicitly:
  * OVERLAPPING ACTION — every bone lags its parent by a few frames, so
    the body never moves as one rigid block. Lag is applied as a phase
    shift; for cyclic clips the keys are also emitted one period before
    and after, which makes the loop tangents wrap correctly (a seam-free
    seamless loop instead of a hitch at frame 1).
  * CURVES — per-keyframe interpolation/easing (SINE/QUAD/BACK with
    EASE_IN / EASE_OUT) instead of one flat auto-bezier everywhere:
    slow-out of anticipation, snap into contacts, float at the apex.
  * BREAKDOWNS — off-midpoint in-betweens so arcs favour one extreme.
  * MOVING HOLDS — the idle never truly stops.
"""
import bpy, sys, math, os
from mathutils import Vector

_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC_IN = _argv[0]
BASE = _argv[1] if len(_argv) > 1 else "."
WHICH = _argv[2] if len(_argv) > 2 else "all"
os.makedirs(BASE, exist_ok=True)
_here = os.path.dirname(os.path.abspath(__file__))
_rig = open(os.path.join(_here, "autorig.py")).read().split(
    chr(10) + 'if __name__ == "__main__":')[0]
exec(_rig)
SRC = SRC_IN
FPS, RES = 24, 640

# lag in frames per bone: the further down the chain, the later it moves
LAG = {"Root": 0, "Hips": 0, "Spine": 1, "Chest": 2, "Head": 3, "Antenna": 6,
       "Clav.L": 2, "Clav.R": 2, "UpperArm.L": 3, "UpperArm.R": 3,
       "Forearm.L": 5, "Forearm.R": 5, "Hand.L": 6, "Hand.R": 6,
       "Thigh.L": 0, "Thigh.R": 0, "Shin.L": 1, "Shin.R": 1,
       "Foot.L": 2, "Foot.R": 2}

EASE = {                       # name -> (interpolation, easing)
    "auto":   ("BEZIER", "AUTO"),
    "smooth": ("SINE", "EASE_IN_OUT"),
    "out":    ("SINE", "EASE_OUT"),      # fast start, settle
    "in":     ("SINE", "EASE_IN"),       # slow start, accelerate
    "snap":   ("QUAD", "EASE_IN"),       # drive hard into the next pose
    "punch":  ("BACK", "EASE_OUT"),      # overshoot on impact
    "float":  ("QUAD", "EASE_IN_OUT"),   # airborne hang
    "linear": ("LINEAR", "AUTO"),
}


class Clip:
    """Collects keys, applies per-bone lag, emits cyclic copies."""

    def __init__(self, name, length, cyclic=True):
        self.name, self.length, self.cyclic = name, length, cyclic
        self.keys = []          # (bone, frame, channel, value, ease)

    def pose(self, frame, ease="auto", **bones):
        for bone, vals in bones.items():
            bone = bone.replace("__", ".")
            if bone in ("root_loc", "root_scale"):
                continue
            self.keys.append((bone, frame, "rot", vals, ease))

    def root(self, frame, loc=None, scale=None, ease="auto"):
        if loc:
            self.keys.append(("Root", frame, "loc", loc, ease))
        if scale:
            self.keys.append(("Root", frame, "scale", scale, ease))

    def apply(self, rig):
        act = bpy.data.actions.new(self.name)
        rig.animation_data_create()
        rig.animation_data.action = act
        reps = (-1, 0, 1) if self.cyclic else (0,)
        for bone, frame, chan, vals, ease in self.keys:
            if bone not in rig.pose.bones:
                continue
            pb = rig.pose.bones[bone]
            pb.rotation_mode = 'XYZ'
            for r in reps:
                f = frame + LAG.get(bone, 0) + r * self.length
                if chan == "rot":
                    pb.rotation_euler = tuple(math.radians(a) for a in vals)
                    pb.keyframe_insert('rotation_euler', frame=f)
                elif chan == "loc":
                    pb.location = vals
                    pb.keyframe_insert('location', frame=f)
                else:
                    pb.scale = vals
                    pb.keyframe_insert('scale', frame=f)
                for fc in act.fcurves:
                    if pb.name not in fc.data_path:
                        continue
                    for kp in fc.keyframe_points:
                        if abs(kp.co.x - f) < 1e-4:
                            kp.interpolation, kp.easing = EASE[ease]
                            kp.handle_left_type = 'AUTO_CLAMPED'
                            kp.handle_right_type = 'AUTO_CLAMPED'
        return act


# ---------------------------------------------------------------- clips
def clip_idle():
    """3s breathing loop. Chest leads, head and antenna trail, weight
    shifts side to side — a moving hold, never a freeze."""
    c = Clip("Idle", 72)
    P = [
        (1,  dict(Hips=(0, 0, 0), Spine=(0, 0, 0), Chest=(0, 0, 0),
                  Head=(0, 0, 0), Antenna=(0, 0, 0),
                  UpperArm__L=(0, 0, 0), UpperArm__R=(0, 0, 0),
                  Forearm__L=(0, 0, 0), Forearm__R=(0, 0, 0)), 0.0, "smooth"),
        (18, dict(Hips=(0, 1.5, 0), Spine=(-2.2, 0, 1.5), Chest=(-3.0, 0, 2.0),
                  Head=(2.0, 0, -2.5), Antenna=(-6, 0, 3),
                  UpperArm__L=(-5, 0, -3), UpperArm__R=(4, 0, 2),
                  Forearm__L=(-4, 0, 0), Forearm__R=(3, 0, 0)), 0.020, "smooth"),
        (36, dict(Hips=(0, 0, 0), Spine=(0.6, 0, 0), Chest=(0.5, 0, 0),
                  Head=(-0.5, 0, 0), Antenna=(3, 0, 0),
                  UpperArm__L=(1, 0, 0), UpperArm__R=(-1, 0, 0),
                  Forearm__L=(1, 0, 0), Forearm__R=(-1, 0, 0)), 0.002, "smooth"),
        (54, dict(Hips=(0, -1.5, 0), Spine=(-2.2, 0, -1.5), Chest=(-3.0, 0, -2.0),
                  Head=(2.0, 0, 2.5), Antenna=(-6, 0, -3),
                  UpperArm__L=(4, 0, 3), UpperArm__R=(-5, 0, -2),
                  Forearm__L=(3, 0, 0), Forearm__R=(-4, 0, 0)), 0.020, "smooth"),
        (73, dict(Hips=(0, 0, 0), Spine=(0, 0, 0), Chest=(0, 0, 0),
                  Head=(0, 0, 0), Antenna=(0, 0, 0),
                  UpperArm__L=(0, 0, 0), UpperArm__R=(0, 0, 0),
                  Forearm__L=(0, 0, 0), Forearm__R=(0, 0, 0)), 0.0, "smooth"),
    ]
    for f, bones, bz, ease in P:
        c.pose(f, ease=ease, **bones)
        c.root(f, loc=(0, 0, bz), ease=ease)
    return c, 72


def clip_walk():
    """32f cycle. Real walk mechanics: contact / down / passing / up,
    knees bending on the swing, feet rolling, hips twisting, arms
    counter-swinging with the forearms trailing."""
    c = Clip("Walk", 32)
    # (frame, thighL, shinL, footL, thighR, shinR, footR, hipTwist, roll, bz, ease)
    K = [
        (1,  26, -8,  6, -20, -30, 12,  8, -2.5, 0.008, "snap"),   # contact L
        (5,  16, -14, -4, -12, -20, 4,   5, -4.0, -0.014, "out"),  # down
        (9,  4,  -10, -6,  6,  -34, -2,  0, -1.5, 0.006, "auto"),  # passing
        (13, -10, -6, -2,  20, -26, 6,  -5, 1.5, 0.016, "in"),     # up
        (17, -20, -30, 12, 26,  -8, 6,  -8, 2.5, 0.008, "snap"),   # contact R
        (21, -12, -20, 4,  16, -14, -4, -5, 4.0, -0.014, "out"),
        (25, 6,  -34, -2,  4,  -10, -6,  0, 1.5, 0.006, "auto"),
        (29, 20, -26, 6, -10,  -6, -2,   5, -1.5, 0.016, "in"),
        (33, 26, -8,  6, -20, -30, 12,   8, -2.5, 0.008, "snap"),
    ]
    for f, tL, sL, fL, tR, sR, fR, twist, roll, bz, ease in K:
        c.pose(f, ease=ease,
               Hips=(0, roll * 0.4, twist),
               Spine=(-1.5, roll * 0.3, -twist * 0.35),
               Chest=(-2.0, roll * 0.2, -twist * 0.5),
               Head=(1.5, -roll * 0.4, twist * 0.25),
               Antenna=(-roll * 1.6, 0, -twist * 0.8),
               Thigh__L=(tL, 0, 0), Shin__L=(sL, 0, 0), Foot__L=(fL, 0, 0),
               Thigh__R=(tR, 0, 0), Shin__R=(sR, 0, 0), Foot__R=(fR, 0, 0),
               Clav__L=(0, 0, -twist * 0.3), Clav__R=(0, 0, -twist * 0.3),
               UpperArm__L=(-tL * 0.55, 0, 0), UpperArm__R=(-tR * 0.55, 0, 0),
               Forearm__L=(-abs(tL) * 0.25 - 6, 0, 0),
               Forearm__R=(-abs(tR) * 0.25 - 6, 0, 0),
               Hand__L=(0, 0, 0), Hand__R=(0, 0, 0))
        c.root(f, loc=(0, 0, bz), ease=ease)
    return c, 32


def clip_hop():
    """60f frog hop, non-cyclic. Anticipation -> launch -> float -> land
    -> settle, with squash & stretch on the ground-anchored Root and a
    late antenna whip."""
    c = Clip("Hop", 60, cyclic=False)
    K = [
        # f,  z,     sqz,  hips, spine, thigh, shin, foot, arm, fore, head, ease
        (1,   0.0,   1.00,  0,   0,     0,    0,    0,    0,   -6,   0,   "in"),
        (10, -0.052, 0.90,  14,  10,    38,  -52,   18,  -32,  -22,  10,  "out"),
        (15, -0.070, 0.86,  18,  13,    46,  -62,   22,  -42,  -30,  14,  "snap"),
        (20,  0.060, 1.12, -14, -10,   -18,  -6,   -14,  38,   -8,  -14,  "punch"),
        (26,  0.235, 1.06,  -8,  -6,   -26,  -18,  -20,  56,   -4,   -9,  "float"),
        (32,  0.245, 1.04,  -4,  -3,   -22,  -22,  -18,  58,   -6,   -6,  "float"),
        (39,  0.075, 1.02,   6,   4,     14,  -30,   6,   26,  -16,   6,  "in"),
        (44, -0.048, 0.89,  16,  12,    40,  -56,   20,  -14,  -26,  12,  "punch"),
        (49,  0.014, 1.05,  -5,  -4,    -8,  -12,  -4,    8,   -8,  -5,   "out"),
        (54, -0.006, 0.99,   2,   2,     4,   -6,    2,   -3,   -7,   2,  "smooth"),
        (60,  0.0,   1.00,   0,   0,     0,    0,    0,    0,   -6,   0,  "smooth"),
    ]
    for f, z, sq, hips, spine, thigh, shin, foot, arm, fore, head, ease in K:
        c.pose(f, ease=ease,
               Hips=(hips, 0, 0), Spine=(spine, 0, 0), Chest=(spine * 0.7, 0, 0),
               Head=(head, 0, 0), Antenna=(-head * 2.2, 0, 0),
               Thigh__L=(thigh, 0, 0), Thigh__R=(thigh, 0, 0),
               Shin__L=(shin, 0, 0), Shin__R=(shin, 0, 0),
               Foot__L=(foot, 0, 0), Foot__R=(foot, 0, 0),
               UpperArm__L=(arm, 0, 0), UpperArm__R=(arm, 0, 0),
               Forearm__L=(fore, 0, 0), Forearm__R=(fore, 0, 0))
        c.root(f, loc=(0, 0, z), scale=(1, 1, sq), ease=ease)
    return c, 60


def clip_turntable():
    c = Clip("Turntable", 96, cyclic=False)
    for f, deg in ((1, 0), (96, 360)):
        c.keys.append(("Root", f, "rot", (0, 0, deg), "linear"))
    return c, 96


CLIPS = {"idle": clip_idle, "walk": clip_walk, "hop": clip_hop,
         "turntable": clip_turntable}


def render_mp4(scene, path, f0, f1):
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


if __name__ == "__main__":
    obj = load_and_normalize(SRC)
    rig = build_armature()
    bind(obj, rig)
    mask_weights(obj, rig, " pre")
    polish_weights(obj)
    mask_weights(obj, rig, " post")
    scene, cam = setup_render(RES)
    scene.render.fps = FPS
    bpy.context.view_layer.objects.active = rig

    todo = list(CLIPS) if WHICH == "all" else [WHICH]
    for name in todo:
        clip, length = CLIPS[name]()
        clip.apply(rig)
        render_mp4(scene, f"{BASE}/{name}.mp4", 1, length)
        print(f"CLIP {name} ({length}f) done")

    for name in CLIPS:
        if name not in todo:
            CLIPS[name]()[0].apply(rig)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=f"{BASE}/animated.glb", use_selection=True,
                              export_animations=True, export_animation_mode='ACTIONS')
    print("ANIM PRO DONE")
