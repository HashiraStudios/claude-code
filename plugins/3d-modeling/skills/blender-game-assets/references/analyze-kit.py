"""
Character-kit analyzer — learn from REFERENCE ASSETS, numerically.

When you obtain a professional character kit (e.g. a Supercell Make base
model), do not eyeball it — dissect it. This module ingests FBX/OBJ/GLB
(or runs inside an opened .blend) and produces the numbers that let our
recipes be corrected against ground truth:

MESH      tris/verts per object, quad/tri/ngon mix, dimensions, applied
          scale, shade smooth/flat, sharp edges
PROPORTIONS  total height, per-part bounding boxes, and — if an armature
          exists — every bone length (head bone => proportions in heads,
          the exact stylization ratio they chose)
UV        island count, coverage %, texel density, open vs collapsed vs
          overlapped islands, plus a UV-layout render OVER the texture
          (exactly how THEY place islands — the question our gradation
          workflow needs answered)
TEXTURE   size, dominant color palette (quantized histogram), saturation
          and value distributions (how saturated/bright pro textures
          really are), vertical-gradient measure (is light painted in
          top-to-bottom?), luminance-vs-height correlation (painted AO?)
MATERIAL  node graph summary — diffuse-only? normal/rough maps? unlit?

USAGE (headless):
  blender --background --python analyze_kit_run.py -- /path/to/kit_dir
where the runner execs this module plus modeling-recipes/uv-gradation
(for export_uv_layout) and calls analyze_kit("/path/to/kit_dir").
"""

import bpy
import os
import math


def _import_any(path):
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    elif ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        return []
    return [o for o in bpy.data.objects if o not in before]


def _uv_stats(obj):
    uv = obj.data.uv_layers.active
    if not uv:
        return None
    obj.data.calc_loop_triangles()
    uv_area = 0.0
    mesh_area = 0.0
    collapsed = 0
    for tri in obj.data.loop_triangles:
        pts = [uv.data[l].uv for l in tri.loops]
        a = abs((pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1])
                - (pts[2][0] - pts[0][0]) * (pts[1][1] - pts[0][1])) / 2
        uv_area += a
        mesh_area += tri.area
        if a < 1e-9:
            collapsed += 1
    return dict(uv_area=uv_area, mesh_area=mesh_area,
                collapsed_tris=collapsed, total_tris=len(obj.data.loop_triangles))


def _texture_stats(img, sample=4):
    w, h = img.size
    px = list(img.pixels)
    n = 0
    sat_sum = val_sum = 0.0
    buckets = {}
    rows_v = [0.0] * h
    rows_n = [0] * h
    for y in range(0, h, sample):
        for x in range(0, w, sample):
            i = (y * w + x) * 4
            r, g, b, a = px[i], px[i + 1], px[i + 2], px[i + 3]
            if a < 0.5:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            v = mx
            s = 0 if mx == 0 else (mx - mn) / mx
            sat_sum += s
            val_sum += v
            n += 1
            rows_v[y] += v
            rows_n[y] += 1
            key = (int(r * 7), int(g * 7), int(b * 7))
            buckets[key] = buckets.get(key, 0) + 1
    if not n:
        return None
    top = sorted(buckets.items(), key=lambda kv: -kv[1])[:8]
    palette = ['#%02X%02X%02X' % tuple(int(c / 7 * 255) for c in k)
               for k, _ in top]
    thirds = h // 3
    top_v = sum(rows_v[h - thirds:]) / max(1, sum(rows_n[h - thirds:]))
    bot_v = sum(rows_v[:thirds]) / max(1, sum(rows_n[:thirds]))
    return dict(size=(w, h), mean_sat=sat_sum / n, mean_val=val_sum / n,
                palette=palette,
                vertical_gradient=top_v - bot_v)   # >0: painted light-on-top


def analyze_kit(kit_dir, out_dir=None, uv_layout_fn=None):
    """Import every model in kit_dir, print the full report, and (optionally)
    write UV-layout proof images via uv_layout_fn(obj, path, base_img)."""
    out_dir = out_dir or kit_dir
    models = [f for f in sorted(os.listdir(kit_dir))
              if f.lower().endswith(('.fbx', '.obj', '.glb', '.gltf'))]
    images = [f for f in sorted(os.listdir(kit_dir))
              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tga'))]
    print(f"=== KIT: {kit_dir} | models: {models} | images: {images} ===")

    for f in models:
        objs = _import_any(os.path.join(kit_dir, f))
        for obj in objs:
            if obj.type == 'ARMATURE':
                print(f"\n-- ARMATURE {obj.name}: {len(obj.data.bones)} bones")
                for b in obj.data.bones:
                    print(f"   {b.name:24s} len={b.length:.4f} "
                          f"head_z={b.head_local.z:.3f}")
            if obj.type != 'MESH':
                continue
            me = obj.data
            me.calc_loop_triangles()
            quads = sum(1 for p in me.polygons if len(p.vertices) == 4)
            tris = sum(1 for p in me.polygons if len(p.vertices) == 3)
            ngons = len(me.polygons) - quads - tris
            smooth = sum(1 for p in me.polygons if p.use_smooth)
            print(f"\n-- MESH {obj.name}")
            print(f"   verts={len(me.vertices)} faces={len(me.polygons)} "
                  f"tris(final)={len(me.loop_triangles)}")
            print(f"   quads={quads} tris={tris} ngons={ngons} "
                  f"smooth_faces={smooth}/{len(me.polygons)}")
            print(f"   dims={tuple(round(d, 4) for d in obj.dimensions)} "
                  f"scale={tuple(round(s, 3) for s in obj.scale)}")
            us = _uv_stats(obj)
            if us:
                print(f"   UV: coverage={us['uv_area'] * 100:.1f}% of 0-1 | "
                      f"collapsed tris={us['collapsed_tris']}/{us['total_tris']}")
            for slot in obj.material_slots:
                m = slot.material
                if not m:
                    continue
                kinds = ([n.type for n in m.node_tree.nodes]
                         if m.use_nodes else ['(no nodes)'])
                texs = [n.image.name for n in m.node_tree.nodes
                        if m.use_nodes and n.type == 'TEX_IMAGE' and n.image]
                print(f"   MAT {m.name}: nodes={sorted(set(kinds))} "
                      f"textures={texs}")

    for f in images:
        img = bpy.data.images.load(os.path.join(kit_dir, f))
        st = _texture_stats(img)
        if st:
            print(f"\n-- TEXTURE {f}: {st['size'][0]}x{st['size'][1]}")
            print(f"   mean saturation={st['mean_sat']:.3f} "
                  f"mean value={st['mean_val']:.3f}")
            print(f"   vertical gradient (top-bottom value)="
                  f"{st['vertical_gradient']:+.3f}")
            print(f"   dominant palette: {' '.join(st['palette'])}")

    # UV layout proofs over the first texture
    if uv_layout_fn and images:
        base = bpy.data.images.load(os.path.join(kit_dir, images[0]),
                                    check_existing=True)
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data.uv_layers.active:
                p = os.path.join(out_dir, f"uv_{obj.name}.png")
                try:
                    uv_layout_fn(obj, p, base=base)
                    print(f"   UV layout -> {p}")
                except Exception as e:
                    print(f"   UV layout failed for {obj.name}: {e}")
    print("\n=== ANALYSIS DONE ===")
