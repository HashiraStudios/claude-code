"""Retopology stage with the organic/hard fork.

  blender --background --python retopo.py -- <in.glb> <out.obj> organic 14000
  blender --background --python retopo.py -- <in.glb> <out.obj> hard 30000

organic → QuadriFlow pure quads (deformation-ready). Cleans non-manifold
input first and VERIFIES the quad count (quadriflow silently no-ops on
bad input). hard → edge-preserving decimate (mecha panel lines and other
shallow features mush under any quadriflow density).
Output OBJ is normalized: height 1.0, feet at z=0, centered. Re-import
with forward_axis='NEGATIVE_Z', up_axis='Y' + apply rotation."""
import bpy, bmesh, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, MODE = argv[0], argv[1], argv[2]
TARGET = int(argv[3]) if len(argv) > 3 else (14000 if MODE == "organic" else 30000)

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
if SRC.endswith(".glb") or SRC.endswith(".gltf"):
    bpy.ops.import_scene.gltf(filepath=SRC)
else:
    bpy.ops.wm.obj_import(filepath=SRC, forward_axis='NEGATIVE_Z', up_axis='Y')
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
obj = max(meshes, key=lambda o: len(o.data.polygons))
for o in meshes:
    if o is not obj:
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# keep only the largest connected island (generated meshes ship strays)
bm = bmesh.new(); bm.from_mesh(obj.data); bm.verts.ensure_lookup_table()
seen, comps = set(), []
for v in bm.verts:
    if v.index in seen:
        continue
    stack, comp = [v], []
    while stack:
        cur = stack.pop()
        if cur.index in seen:
            continue
        seen.add(cur.index); comp.append(cur)
        for e in cur.link_edges:
            o2 = e.other_vert(cur)
            if o2.index not in seen:
                stack.append(o2)
    comps.append(comp)
comps.sort(key=len, reverse=True)
stray = [v for c in comps[1:] for v in c]
if stray:
    print(f"[ISLANDS] removing {len(stray)} stray verts in {len(comps)-1} islands")
    bmesh.ops.delete(bm, geom=stray, context='VERTS')
bm.to_mesh(obj.data); bm.free()

# pre-decimate huge marching-cubes output to a workable density
if len(obj.data.polygons) > 260000:
    dec = obj.modifiers.new("dec", 'DECIMATE')
    dec.ratio = 250000 / len(obj.data.polygons)
    bpy.ops.object.modifier_apply(modifier="dec")
print(f"[PRE] tris={len(obj.data.polygons)}")

if MODE == "organic":
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.00005)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.quadriflow_remesh(target_faces=TARGET, use_mesh_symmetry=True,
                                     use_preserve_sharp=False,
                                     use_preserve_boundary=False, seed=7)
    quads = sum(1 for p in obj.data.polygons if len(p.vertices) == 4)
    print(f"[RETOPO] polys={len(obj.data.polygons)} quads={quads}")
    assert quads > 0, "quadriflow no-op — input still non-manifold"
else:
    dec2 = obj.modifiers.new("dec2", 'DECIMATE')
    dec2.ratio = TARGET / len(obj.data.polygons)
    bpy.ops.object.modifier_apply(modifier="dec2")
    print(f"[RETOPO] tris={len(obj.data.polygons)}")

# normalize: height 1.0, feet z=0, centered
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

bpy.ops.wm.obj_export(filepath=OUT, export_selected_objects=True)
print(f"RETOPO DONE -> {OUT}")
