"""Professional biped rig: measured joint pivots, heat skinning with
soft anatomical masks, and deformation tests.

  blender --background --python autorig.py -- <painted.glb> <outdir>

Pipeline: weld seam-duplicate verts -> build the chained skeleton ->
bone-heat skinning -> soft region masks -> limit4/normalize/smooth ->
six deformation-test renders you MUST look at before animating.

Chain per side: Clavicle -> UpperArm -> Forearm -> Hand
                Thigh -> Shin -> Foot
Spine: Hips -> Spine -> Chest -> Head, all under an unweighted Root.

Skinning: bone-heat (smooth falloff by construction) with an analytic
distance-to-segment fallback, then limit-4 + normalize + light smooth.
RULE: no vertex may sit at weight 1.0 on a joint — the blend zone is
what stops the creasing/tearing.

Writes deformation-test renders so the joints can be judged before any
animation work.
"""
import bpy, bmesh, sys, math, os
from mathutils import Vector

import sys
_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC = _argv[0] if _argv else None
OUTDIR = _argv[1] if len(_argv) > 1 else "."
BASE = OUTDIR

# ---- measured skeleton (see analyze_joints.py output) -------------------
SK = {
    "Root":      ((0, 0, 0.0),      (0, 0, 0.12),      None,  False),
    "Hips":      ((0, 0, 0.40),     (0, 0, 0.52),      "Root", True),
    "Spine":     ((0, 0, 0.52),     (0, 0, 0.64),      "Hips", True),
    "Chest":     ((0, 0, 0.64),     (0, -0.02, 0.74),  "Spine", True),
    "Head":      ((0, -0.02, 0.74), (0, -0.05, 0.99),  "Chest", True),
    # thin antenna: its own bone so it can lag and whip (follow-through)
    "Antenna":   ((0, -0.01, 0.925), (0, -0.01, 1.05),  "Head", True),
}
for sx, s in ((-1, "L"), (1, "R")):
    SK[f"Clav.{s}"]     = ((sx * 0.10, 0, 0.665), (sx * 0.27, -0.01, 0.61), "Chest", True)
    SK[f"UpperArm.{s}"] = ((sx * 0.27, -0.01, 0.61), (sx * 0.335, -0.03, 0.36), f"Clav.{s}", True)
    SK[f"Forearm.{s}"]  = ((sx * 0.335, -0.03, 0.36), (sx * 0.425, -0.03, 0.305), f"UpperArm.{s}", True)
    SK[f"Hand.{s}"]     = ((sx * 0.425, -0.03, 0.305), (sx * 0.478, -0.055, 0.29), f"Forearm.{s}", True)
    SK[f"Thigh.{s}"]    = ((sx * 0.130, 0, 0.42), (sx * 0.165, 0.005, 0.315), "Hips", True)
    SK[f"Shin.{s}"]     = ((sx * 0.165, 0.005, 0.315), (sx * 0.155, 0.02, 0.12), f"Thigh.{s}", True)
    SK[f"Foot.{s}"]     = ((sx * 0.155, 0.02, 0.12), (sx * 0.150, -0.10, 0.02), f"Shin.{s}", True)
ORDER = ["Root", "Hips", "Spine", "Chest", "Head", "Antenna"] + \
        [f"{b}.{s}" for s in "LR" for b in
         ("Clav", "UpperArm", "Forearm", "Hand", "Thigh", "Shin", "Foot")]


def load_and_normalize(path):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    for o in meshes:
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = "Character"
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    s = 1.0 / (hi.z - lo.z)
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    obj.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # CRITICAL: a GLB duplicates vertices at every UV/normal seam. Those
    # twins get different weights and TEAR APART when deformed (425
    # disconnected components on this asset). Weld before rigging —
    # Blender keeps UVs per-loop, so the texture is untouched.
    import bmesh as _bm
    _b = _bm.new(); _b.from_mesh(obj.data)
    before = len(_b.verts)
    _bm.ops.remove_doubles(_b, verts=_b.verts, dist=1e-4)
    _b.to_mesh(obj.data); _b.free()
    obj.data.update()
    print(f"[WELD] {before} -> {len(obj.data.vertices)} verts")
    for p in obj.data.polygons:
        p.use_smooth = True
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(42)
    return obj


def build_armature():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    rig = bpy.context.active_object
    rig.name = "RigPro"
    ebs = rig.data.edit_bones
    ebs.remove(ebs[0])
    for name in ORDER:
        head, tail, parent, deform = SK[name]
        b = ebs.new(name)
        b.head, b.tail = head, tail
        b.use_deform = deform
        b.use_connect = False
        if parent:
            b.parent = ebs[parent]
    bpy.ops.armature.select_all(action='SELECT')
    bpy.ops.armature.calculate_roll(type='GLOBAL_POS_Z')
    bpy.ops.object.mode_set(mode='OBJECT')
    return rig


def seg_distance(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    return (p - (a + ab * t)).length


def analytic_weights(obj, rig, power=2.6, max_inf=4):
    """Fallback / repair: smooth inverse-distance-to-segment weights."""
    deform = [(b.name, Vector(SK[b.name][0]), Vector(SK[b.name][1]))
              for b in rig.data.bones if b.use_deform]
    for v in obj.data.vertices:
        ws = []
        for name, a, b in deform:
            d = seg_distance(v.co, a, b)
            ws.append((name, 1.0 / (d ** power + 1e-6)))
        ws.sort(key=lambda t: -t[1])
        ws = ws[:max_inf]
        tot = sum(w for _, w in ws)
        for name, w in ws:
            obj.vertex_groups[name].add([v.index], w / tot, 'REPLACE')


def bind(obj, rig):
    for o in bpy.data.objects:
        o.select_set(False)
    obj.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        mode = "bone-heat"
    except Exception as e:
        print("heat failed:", e)
        bpy.ops.object.parent_set(type='ARMATURE_NAME')
        mode = "name"
    for b in rig.data.bones:
        if b.use_deform and b.name not in obj.vertex_groups:
            obj.vertex_groups.new(name=b.name)
    empty = [v for v in obj.data.vertices
             if not v.groups or all(g.weight < 1e-4 for g in v.groups)]
    print(f"[BIND] {mode}: empty={len(empty)}/{len(obj.data.vertices)}")
    if empty:
        print("[BIND] filling gaps analytically")
        deform = [(b.name, Vector(SK[b.name][0]), Vector(SK[b.name][1]))
                  for b in rig.data.bones if b.use_deform]
        for v in empty:
            ws = sorted(((n, 1.0 / (seg_distance(v.co, a, b) ** 2.6 + 1e-6))
                         for n, a, b in deform), key=lambda t: -t[1])[:4]
            tot = sum(w for _, w in ws)
            for n, w in ws:
                obj.vertex_groups[n].add([v.index], w / tot, 'REPLACE')
    return mode



# ---- anatomical region masks with SOFT falloff -------------------------
# A binary in/out mask re-creates hard weight edges (the head tore off the
# body at the region boundary). Regions therefore return a signed margin
# and the weight is attenuated smoothly across a transition band.
def _side(n):
    return -1 if n.endswith(".L") else (1 if n.endswith(".R") else 0)

BAND = 0.07


def _margin(base, x, y, z, s):
    if base == "Antenna":  return min(0.055 - abs(x), z - 0.90)
    if base == "Head":     return z - 0.60
    if base == "Chest":    return min(z - 0.42, 0.90 - z)
    if base == "Spine":    return min(z - 0.26, 0.78 - z)
    if base == "Hips":     return 0.66 - z
    if base == "Clav":     return min(s * x - 0.04, z - 0.46, 0.84 - z)
    if base == "UpperArm": return min(s * x - 0.17, z - 0.22, 0.78 - z)
    if base == "Forearm":  return min(s * x - 0.25, z - 0.14, 0.64 - z)
    if base == "Hand":     return min(s * x - 0.33, 0.54 - z)
    if base == "Thigh":    return min(s * x - 0.005, 0.29 - s * x, 0.54 - z)
    if base == "Shin":     return min(s * x - 0.005, 0.29 - s * x, 0.42 - z)
    if base == "Foot":     return min(s * x - 0.005, 0.29 - s * x, 0.24 - z)
    return 1.0


def _smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def mask_weights(obj, rig, label=""):
    """Attenuate each weight by how far the vertex sits outside its bone's
    anatomical region — smooth over BAND, never a hard cut. Stops arm
    bones grabbing the chest without tearing at the boundary."""
    gname = {g.index: g.name for g in obj.vertex_groups}
    cut = 0.0
    for v in obj.data.vertices:
        keep = []
        for g in v.groups:
            name = gname[g.group]
            f = _smoothstep(_margin(name.split(".")[0], v.co.x, v.co.y, v.co.z,
                                    _side(name)) / BAND + 0.5)
            w = g.weight * f
            cut += g.weight - w
            if w > 1e-4:
                keep.append((name, w))
        if not keep:
            deform = [(b.name, Vector(SK[b.name][0]), Vector(SK[b.name][1]))
                      for b in rig.data.bones if b.use_deform]
            keep = sorted(((n, 1.0 / (seg_distance(v.co, a, b) ** 2.6 + 1e-6))
                           for n, a, b in deform), key=lambda t: -t[1])[:3]
        tot = sum(w for _, w in keep)
        for gi in [g.group for g in v.groups]:
            obj.vertex_groups[gname[gi]].remove([v.index])
        for n, w in keep:
            obj.vertex_groups[n].add([v.index], w / tot, 'REPLACE')
    print(f"[MASK{label}] attenuated {cut:.0f} weight-units of bleed")


def polish_weights(obj):
    """limit to 4 influences, normalize, then a light smooth so the joint
    blend spans a few loops (the anti-crease rule)."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_smooth(group_select_mode='ALL',
                                       factor=0.5, repeat=2, expand=0.0)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL',
                                              lock_active=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    # QA: how many verts are still fully rigid on one bone?
    rigid = sum(1 for v in obj.data.vertices
                if max((g.weight for g in v.groups), default=0) > 0.995)
    multi = sum(1 for v in obj.data.vertices
                if sum(1 for g in v.groups if g.weight > 0.05) >= 2)
    print(f"[WEIGHTS] rigid(>0.995)={rigid}  blended(2+ bones)={multi} "
          f"/{len(obj.data.vertices)}")


def setup_render(res=640):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = res
    scene.eevee.taa_render_samples = 16
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.92, 0.9, 1)
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
    return scene, cam


def deform_test(rig, obj, scene):
    """Extreme single-joint poses — the honest way to judge a rig."""
    tests = {
        "arm_up":    [("UpperArm.L", (0, 0, -85))],
        "arm_fwd":   [("UpperArm.L", (-75, 0, 0))],
        "elbow":     [("UpperArm.L", (-25, 0, 0)), ("Forearm.L", (-95, 0, 0))],
        "knee":      [("Thigh.L", (30, 0, 0)), ("Shin.L", (-55, 0, 0))],
        "spine":     [("Spine", (-22, 0, 0)), ("Chest", (-18, 0, 12)),
                      ("Head", (-12, 0, 18))],
        "crouch":    [("Thigh.L", (34, 0, 0)), ("Shin.L", (-58, 0, 0)),
                      ("Thigh.R", (34, 0, 0)), ("Shin.R", (-58, 0, 0)),
                      ("Spine", (14, 0, 0))],
    }
    bpy.context.view_layer.objects.active = rig
    scene.render.image_settings.file_format = 'PNG'
    for name, pose in tests.items():
        bpy.ops.object.mode_set(mode='POSE')
        for pb in rig.pose.bones:
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (0, 0, 0)
        for bone, rot in pose:
            pb = rig.pose.bones[bone]
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = tuple(math.radians(a) for a in rot)
        bpy.ops.object.mode_set(mode='OBJECT')
        scene.render.filepath = f"{BASE}/deform_{name}.png"
        bpy.ops.render.render(write_still=True)
        print(f"[DEFORM TEST] {name}")
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')


if __name__ == "__main__":
    obj = load_and_normalize(SRC)
    rig = build_armature()
    bind(obj, rig)
    mask_weights(obj, rig, " pre")
    polish_weights(obj)
    mask_weights(obj, rig, " post")
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
    bpy.ops.object.vertex_group_normalize_all(group_select_mode='ALL',
                                              lock_active=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    scene, cam = setup_render()
    deform_test(rig, obj, scene)
    bpy.ops.wm.save_as_mainfile(filepath=f"{BASE}/frog_rigpro.blend")
    print("RIG PRO DONE")
