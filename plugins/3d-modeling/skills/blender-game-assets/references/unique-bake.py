"""
Unique bake — trim blockout in, hero texture out.

Trim sheets tile GENERIC material everywhere, which caps quality on hero
assets: details can't be POSITIONED (no painted highlight on this
specific bevel, no shadow in that specific crevice), and busy strips
repeat. The pro pipeline (blockbench/hand-painted school): texture with
trims first, then REBAKE everything into one unique UV atlas and paint
positioned details onto it from the geometry itself.

`unique_bake(obj, sheet, rough, metal)`:
  1. Adds a 'BakeUV' layer (smart_project) — unique, non-overlapping.
  2. Rasterizes the trim-mapped look into the atlas: per texel,
     barycentric-interpolates the trim UV and bilinear-samples the sheet
     (U wraps — trim U tiles outside 0..1). Same for rough/metal.
  3. PAINTS THE MESH'S OWN EDGES (the blockbench signature):
       * convex edges + open shell borders -> warm bright stroke
       * concave edges -> saturated violet shadow stroke
     drawn in UV space along each face's loops, so every bevel catches a
     highlight exactly where a hand-painter would put one.
  4. Derives the normal map from the unique albedo, marks BakeUV as the
     render UV set, and swaps in a single-texture PBR material.

Use trims alone for kit/background pieces; run unique_bake on heroes.
Texel budget: pure-Python rasterize — 768px is the sweet spot (~1 min);
1024 for closeups. Run BEFORE grade_object (it patches the new
material's Base Color with the vertex grade).
"""

import bpy
import math
from mathutils import Vector


def _bilinear(px, w, h, u, v):
    u = u % 1.0
    v = min(0.999, max(0.0, v))
    fx, fy = u * (w - 1), v * (h - 1)
    ix, iy = int(fx), int(fy)
    tx, ty = fx - ix, fy - iy
    ix2, iy2 = min(w - 1, ix + 1), min(h - 1, iy + 1)
    out = []
    for c in range(3):
        top = px[(iy * w + ix) * 4 + c] * (1 - tx) + px[(iy * w + ix2) * 4 + c] * tx
        bot = px[(iy2 * w + ix) * 4 + c] * (1 - tx) + px[(iy2 * w + ix2) * 4 + c] * tx
        out.append(top * (1 - ty) + bot * ty)
    return out


def unique_bake(obj, sheet_img, rough_img=None, metal_img=None, size=768,
                edge_angle=26.0, name="Unique", path_prefix=None):
    """Rebake `obj`'s trim-mapped look into a unique atlas with painted
    edges, swap in the hero material, return it."""
    # 1. unique UVs
    if 'BakeUV' not in obj.data.uv_layers:
        obj.data.uv_layers.new(name='BakeUV')
    obj.data.uv_layers.active = obj.data.uv_layers['BakeUV']
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.015)
    bpy.ops.object.mode_set(mode='OBJECT')

    mesh = obj.data
    uv_trim = mesh.uv_layers['UVMap']
    uv_bake = mesh.uv_layers['BakeUV']
    sw, sh = sheet_img.size
    spx = list(sheet_img.pixels)
    aux = []
    for img in (rough_img, metal_img):
        if img is not None:
            aux.append((list(img.pixels), img.size[0], img.size[1]))
        else:
            aux.append(None)

    A = [0.0] * (size * size * 4)
    R = [0.5] * (size * size * 4) if aux[0] else None
    M = [0.0] * (size * size * 4) if aux[1] else None

    # 2. rasterize trim look -> atlas (barycentric UV interp + bilinear)
    mesh.calc_loop_triangles()
    for tri in mesh.loop_triangles:
        bpts = [uv_bake.data[l].uv for l in tri.loops]
        tpts = [uv_trim.data[l].uv for l in tri.loops]
        xs = [p[0] * size for p in bpts]
        ys = [p[1] * size for p in bpts]
        x0, x1 = max(0, int(min(xs)) - 1), min(size - 1, int(max(xs)) + 1)
        y0, y1 = max(0, int(min(ys)) - 1), min(size - 1, int(max(ys)) + 1)
        ax, ay, bx, by, cx, cy = xs[0], ys[0], xs[1], ys[1], xs[2], ys[2]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-9:
            continue
        for yy in range(y0, y1 + 1):
            for xx in range(x0, x1 + 1):
                w0 = ((by - cy) * (xx + 0.5 - cx) + (cx - bx) * (yy + 0.5 - cy)) / d
                w1 = ((cy - ay) * (xx + 0.5 - cx) + (ax - cx) * (yy + 0.5 - cy)) / d
                w2 = 1 - w0 - w1
                if w0 < -0.08 or w1 < -0.08 or w2 < -0.08:   # outset kills gutters
                    continue
                tu = tpts[0][0] * w0 + tpts[1][0] * w1 + tpts[2][0] * w2
                tv = tpts[0][1] * w0 + tpts[1][1] * w1 + tpts[2][1] * w2
                i4 = (yy * size + xx) * 4
                A[i4:i4 + 3] = _bilinear(spx, sw, sh, tu, tv)
                A[i4 + 3] = 1.0
                if R is not None:
                    R[i4:i4 + 3] = _bilinear(aux[0][0], aux[0][1], aux[0][2], tu, tv)
                    R[i4 + 3] = 1.0
                if M is not None:
                    M[i4:i4 + 3] = _bilinear(aux[1][0], aux[1][1], aux[1][2], tu, tv)
                    M[i4 + 3] = 1.0

    # 3. positioned edge paint: convex/border -> warm stroke, concave -> violet
    edge_faces = {}
    for poly in mesh.polygons:
        for ek in poly.edge_keys:
            edge_faces.setdefault(tuple(sorted(ek)), []).append(poly.index)

    def stroke(p0, p1, kind):
        n = max(2, int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1])) * size))
        for k in range(n + 1):
            t = k / n
            xx = int(p0[0] * size + (p1[0] - p0[0]) * size * t)
            yy = int(p0[1] * size + (p1[1] - p0[1]) * size * t)
            for ox, oy, w in ((0, 0, 1.0), (1, 0, 0.45), (0, 1, 0.45)):
                px_, py_ = xx + ox, yy + oy
                if not (0 <= px_ < size and 0 <= py_ < size):
                    continue
                i4 = (py_ * size + px_) * 4
                if A[i4 + 3] < 0.5:
                    continue
                if kind == 'hi':
                    for c, add in ((0, 0.055), (1, 0.035), (2, 0.010)):
                        A[i4 + c] = min(1.0, A[i4 + c] * (1 + 0.32 * w) + add * w)
                else:
                    for c, m in ((0, 0.62), (1, 0.55), (2, 0.78)):
                        A[i4 + c] = A[i4 + c] * (1 - w + m * w)

    lim = math.radians(edge_angle)
    for ek, faces in edge_faces.items():
        if len(faces) == 1:
            kind = 'hi'                      # open shell border: rim light
            polys = [mesh.polygons[faces[0]]]
        elif len(faces) == 2:
            p1, p2 = mesh.polygons[faces[0]], mesh.polygons[faces[1]]
            if p1.normal.angle(p2.normal, 0.0) < lim:
                continue
            convex = p1.normal.dot(p2.center - p1.center) < 0
            kind = 'hi' if convex else 'lo'
            polys = [p1, p2]
        else:
            continue
        for poly in polys:                   # draw in EACH face's island
            uvs = [uv_bake.data[li].uv for li in poly.loop_indices
                   if mesh.loops[li].vertex_index in ek]
            if len(uvs) == 2:
                stroke(uvs[0], uvs[1], kind)

    def to_img(buf, nm, noncolor=False):
        # data maps: float buffer + colorspace set BEFORE pixels — flipping
        # colorspace after assignment invalidates a byte image's buffer
        # (it re-encodes and the data comes back black)
        img = bpy.data.images.new(nm, width=size, height=size, alpha=False,
                                  float_buffer=noncolor)
        if noncolor:
            img.colorspace_settings.name = 'Non-Color'
        img.pixels = buf
        if path_prefix:
            img.filepath_raw = f"{path_prefix}_{nm.lower()}.png"
            img.file_format = 'PNG'
            img.save()
        return img

    alb = to_img(A, f"{name}Alb")
    rgh = to_img(R, f"{name}Rgh", True) if R is not None else None
    met = to_img(M, f"{name}Met", True) if M is not None else None
    nrm = normal_from_image(alb, f"{name}Nrm", strength=1.2)

    # 4. BakeUV renders; single-texture hero material
    mesh.uv_layers['BakeUV'].active_render = True
    obj.data.materials.clear()
    mat = pbr_material(name, alb, normal_img=nrm, rough_img=rgh,
                       metal_img=met, normal_strength=0.7)
    assign_material(obj, mat)
    return mat
