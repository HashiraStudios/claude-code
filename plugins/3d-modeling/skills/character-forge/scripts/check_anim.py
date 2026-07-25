"""Objective animation QA gate (stage 6b).

  blender --background --python check_anim.py -- <painted.glb>

A still frame hides both of the failures that sank two earlier animation
passes, so both are MEASURED instead of eyeballed:

  CONTACT — the lowest deformed-mesh vertex per frame. 0.000 = standing on
            the floor; negative = the sole is inside the ground.
  REACH   — the distance between the Foot bone's head and its IK target.
            When the pelvis rises past the leg's length the solver quietly
            gives up and the foot unsticks. Nothing looks wrong in a single
            frame; in motion it reads as skating.

Ship only at `problems=0`. If the walk reports OVEREXTENDED at the contact
frames, the pelvis is too high there — the contacts must be the LOWEST
part of the bob, because that is where the stance foot reaches furthest.
"""
import bpy, sys, os

_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
_here = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "--", _argv[0], os.path.dirname(_argv[0]) or "."]
exec(open(os.path.join(_here, "animate_pro.py")).read().split(
    chr(10) + 'if __name__ == "__main__":')[0])

TOL_Z, TOL_REACH, MIN_TRAVEL = 0.012, 0.010, 0.05
obj, rig = build()
scene, cam = setup_stage()
bad = 0
for clip_name in ("walk", "hop", "idle"):
    c, L = CLIPS[clip_name]()
    c.apply(rig)
    print(f"--- {clip_name} ---")
    # IS IT EVEN MOVING? A rig sitting in its rest pose scores PERFECTLY on
    # contact — the sole is exactly on the floor in every frame — so a
    # silent animation failure reads as a flawless result. Measure the path
    # a landmark actually travels before trusting any other number.
    _prev, _travel = None, 0.0
    for f in range(1, L + 1):
        scene.frame_set(f)
        p = rig.matrix_world @ rig.pose.bones["Hand.L"].tail
        if _prev is not None:
            _travel += (p - _prev).length
        _prev = p
    moving = _travel > MIN_TRAVEL
    bad += 0 if moving else 1
    print(f"  travel Hand.L = {_travel:.3f} {'ok' if moving else 'STATIC — clip is dead'}")
    for f in range(1, L + 1, 2):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        me = ev.to_mesh()
        # to_mesh() is OBJECT-LOCAL: without matrix_world this silently
        # measures the wrong space the moment anything moves the object.
        M = ev.matrix_world
        co = [M @ v.co for v in me.vertices]
        zmin = min(p.z for p in co)
        zl = min((p.z for p in co if p.x < -0.03), default=9)
        zr = min((p.z for p in co if p.x > 0.03), default=9)
        ev.to_mesh_clear()
        reach = max((rig.pose.bones[f"Foot.{s}"].head
                     - rig.pose.bones[f"IK.Ankle.{s}"].head).length
                    for s in "LR")
        flags = []
        if zmin < -TOL_Z:
            flags.append("SINK")
        if zmin > TOL_Z and clip_name != "hop":   # the hop is meant to fly
            flags.append("FLOAT")
        if reach > TOL_REACH:
            flags.append("OVEREXTENDED")
        bad += len(flags)
        print(f"  f{f:3d} min={zmin:+.3f} L={zl:+.3f} R={zr:+.3f} "
              f"reach={reach:.3f} {' '.join(flags) or 'ok'}")
print(f"CHECK DONE  problems={bad}")
