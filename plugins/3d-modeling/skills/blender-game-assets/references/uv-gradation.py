"""
Gradation-atlas UVs — the Japanese pro colormap workflow, executable.

THE TECHNIQUE (Kiyotako's palette-atlas method / gradient atlas texturing,
as used across Japanese low-poly game art)
---------------------------------------------------------------------------
The atlas comes FIRST, the model second, and the UV is the paintbrush:

  1. Build a small atlas of vertical GRADATION RAMPS (multi-stop gradients
     with hue-shifted shadows) plus a row of flat cells.
  2. Unwrap meshes into OPEN, RECTANGULAR, AXIS-ALIGNED islands
     (the Japanese 矩形整列 standard: cylinder walls unroll into clean
     rectangles; straight texture lines stay straight on the model).
  3. PLACE each island onto the ramp of the color you want
     ("want the back red? shrink the island and drop it on the red cell").
  4. HACK THE UVs to shade: push island verts DOWN a ramp to paint shadow,
     UP to paint light. The island's shape over the ramp IS the lighting.
  5. Variations for free: shift an island one ramp column sideways and the
     whole prop recolors. Symmetric parts overlap on the same spot.

Flat-cell painting (palette-texturing.py) is the entry level; THIS is the
professional level: open islands + multi-stop ramps + UV-shading.

USAGE
  img = build_gradation_atlas("Pro", RAMPS, FLATS, path=...)
  mat = palette_material("Pro", img)          # from palette-texturing.py
  unwrap_cylinder_open(obj, side_polys)       # open rectangular island
  place_island(obj, side_polys, region('wood'))
  shade_shift(obj, underside_polys, -0.10)    # push down-ramp = paint shadow
  export_uv_layout(obj, "/path/uv.png", base=img)   # proof image
"""

import bpy
import math

ATLAS_SIZE = 128
_REGIONS = {}          # name -> (u0, v0, u1, v1)


def _hex2(c):
    c = c.lstrip('#')
    return [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def region(name):
    """UV rect (u0, v0, u1, v1) of a ramp/cell in the last-built atlas."""
    return _REGIONS[name]


def build_gradation_atlas(name, ramps, flats=None, path=None, size=ATLAS_SIZE):
    """Atlas layout: top 1/8 = flat cells; the rest = vertical ramp columns.
    `ramps`  = list of (name, [(t, hex), ...]) — multi-stop, t: 0 bottom(dark)
               to 1 top(light). Shift hue in the dark stops (cool shadows).
    `flats`  = list of (name, hex) cells across the top row."""
    global _REGIONS
    _REGIONS = {}
    flats = flats or []
    px = [0.0] * (size * size * 4)
    top_h = size // 8
    ramp_h = size - top_h
    ncols = max(1, len(ramps))
    colw = size // ncols

    def put(x, y, rgb):
        i = (y * size + x) * 4
        px[i:i + 3] = rgb
        px[i + 3] = 1.0

    for ci, (rname, stops) in enumerate(ramps):
        x0, x1 = ci * colw, (ci + 1) * colw
        stops = sorted(stops)
        for y in range(0, ramp_h):
            t = y / (ramp_h - 1)
            lo = max([s for s in stops if s[0] <= t], key=lambda s: s[0])
            hi = min([s for s in stops if s[0] >= t], key=lambda s: s[0])
            if lo[0] == hi[0]:
                rgb = _hex2(lo[1])
            else:
                f = (t - lo[0]) / (hi[0] - lo[0])
                a, b = _hex2(lo[1]), _hex2(hi[1])
                rgb = [ai + (bi - ai) * f for ai, bi in zip(a, b)]
            for x in range(x0, x1):
                put(x, y, rgb)
        _REGIONS[rname] = (x0 / size, 0.0, x1 / size, ramp_h / size)

    if flats:
        fw = size // len(flats)
        for fi, (fname, fhex) in enumerate(flats):
            rgb = _hex2(fhex)
            for y in range(ramp_h, size):
                for x in range(fi * fw, (fi + 1) * fw):
                    put(x, y, rgb)
            _REGIONS[fname] = (fi * fw / size, ramp_h / size,
                               (fi + 1) * fw / size, 1.0)

    img = bpy.data.images.new(name, width=size, height=size, alpha=False)
    img.pixels = px
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def gradation_material(name, img):
    """Material for gradation atlases: LINEAR interpolation (smooth ramps —
    'Closest' would band them), clamped extension so shade_shift can't wrap
    into a neighboring ramp."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Linear'
    tex.extension = 'EXTEND'
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.85
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


# ---------------------------------------------------------------------------
# OPEN, ALIGNED UNWRAPS (矩形整列 — rectangular, axis-aligned islands)
# ---------------------------------------------------------------------------

def _uv_layer(obj):
    return obj.data.uv_layers.active or obj.data.uv_layers.new(name="UVMap")


def unwrap_cylinder_open(obj, poly_indices, axis='Z'):
    """Unroll a cylinder/lathe wall into ONE open rectangle:
    U = angle around the axis, V = position along it. The seam lands at the
    back (+axis-adjacent angle wrap handled per loop, since loops own their
    UVs). Result: a perfectly straight, aligned island — texture lines stay
    straight on the model."""
    uv = _uv_layer(obj)
    ai = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    bi, ci = (ai + 1) % 3, (ai + 2) % 3
    polys = [obj.data.polygons[i] for i in poly_indices]
    vs = [obj.data.vertices[vi].co[ai] for p in polys for vi in p.vertices]
    vmin, vmax = min(vs), max(vs)
    vspan = (vmax - vmin) or 1.0
    for p in polys:
        us = {}
        for vi in p.vertices:
            co = obj.data.vertices[vi].co
            us[vi] = math.atan2(co[ci], co[bi]) / (2 * math.pi) + 0.5
        if max(us.values()) - min(us.values()) > 0.5:      # face crosses seam
            us = {vi: (u + 1.0 if u < 0.5 else u) for vi, u in us.items()}
        for li, vi in zip(p.loop_indices, p.vertices):
            co = obj.data.vertices[vi].co
            uv.data[li].uv = (us[vi], (co[ai] - vmin) / vspan)


def unwrap_planar(obj, poly_indices, axis='Y'):
    """Planar projection along an axis (the classic z/y-projection used in
    mobile gradient texturing). The island keeps the silhouette's shape —
    ideal for dropping onto a ramp so height = shade."""
    uv = _uv_layer(obj)
    ai = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    ua, va = ((0, 1) if ai == 2 else ((1, 2) if ai == 0 else (0, 2)))
    for pi in poly_indices:
        p = obj.data.polygons[pi]
        for li, vi in zip(p.loop_indices, p.vertices):
            co = obj.data.vertices[vi].co
            uv.data[li].uv = (co[ua], co[va])


def place_island(obj, poly_indices, rect, margin=0.06, keep_aspect=False):
    """Normalize the current UVs of these polys and fit them into `rect`
    (u0, v0, u1, v1) — 'shrink the island and drop it on the color you want'.
    margin is fractional inside the rect (keeps samples off ramp borders)."""
    uv = _uv_layer(obj)
    lis = [li for pi in poly_indices
           for li in obj.data.polygons[pi].loop_indices]
    if not lis:
        print("place_island: empty selection — check your predicate")
        return
    us = [uv.data[li].uv[0] for li in lis]
    vs = [uv.data[li].uv[1] for li in lis]
    umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
    uspan, vspan = (umax - umin) or 1.0, (vmax - vmin) or 1.0
    u0, v0, u1, v1 = rect
    mw, mh = (u1 - u0) * margin, (v1 - v0) * margin
    tw, th = (u1 - u0) - 2 * mw, (v1 - v0) - 2 * mh
    su, sv = tw / uspan, th / vspan
    if keep_aspect:
        su = sv = min(su, sv)
    # center the island in the region — shade_shift decides up/down from there
    ou = u0 + mw + (tw - uspan * su) / 2
    ov = v0 + mh + (th - vspan * sv) / 2
    for li in lis:
        u, v = uv.data[li].uv
        uv.data[li].uv = (ou + (u - umin) * su, ov + (v - vmin) * sv)


def shade_shift(obj, poly_indices, dv):
    """THE UV HACK: slide these polys' UVs along V within their ramp.
    Negative dv = down-ramp = painted shadow; positive = light. Use on
    undersides, crevices, or to pop one plank lighter than its neighbors."""
    uv = _uv_layer(obj)
    for pi in poly_indices:
        for li in obj.data.polygons[pi].loop_indices:
            u, v = uv.data[li].uv
            uv.data[li].uv = (u, v + dv)


def recolor_shift(obj, poly_indices, columns):
    """Free variation: shift islands sideways N ramp columns — the whole
    part recolors without touching geometry or memory."""
    uv = _uv_layer(obj)
    du = columns / max(1, len(_REGIONS))
    for pi in poly_indices:
        for li in obj.data.polygons[pi].loop_indices:
            u, v = uv.data[li].uv
            uv.data[li].uv = (u + du, v)


# ---------------------------------------------------------------------------
# PROOF IMAGE — atlas + UV wireframe overlay
# ---------------------------------------------------------------------------

def export_uv_layout(obj, path, base=None, size=512):
    """Render the UV layout over the atlas to a PNG: the professional
    deliverable that shows open, aligned islands sitting on their ramps."""
    px = [0.0] * (size * size * 4)
    if base:
        bw, bh = base.size
        bpx = list(base.pixels)
        for y in range(size):
            for x in range(size):
                bx, by = int(x * bw / size), int(y * bh / size)
                si, di = (by * bw + bx) * 4, (y * size + x) * 4
                px[di:di + 3] = [c * 0.75 for c in bpx[si:si + 3]]
                px[di + 3] = 1.0

    def dot(x, y):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 4
            px[i:i + 4] = [1.0, 1.0, 1.0, 1.0]

    def line(x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            dot(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy; x0 += sx
            if e2 <= dx:
                err += dx; y0 += sy

    uv = obj.data.uv_layers.active
    for p in obj.data.polygons:
        pts = [uv.data[li].uv for li in p.loop_indices]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            line(int(a[0] * (size - 1)), int(a[1] * (size - 1)),
                 int(b[0] * (size - 1)), int(b[1] * (size - 1)))

    img = bpy.data.images.new("UVLayout", width=size, height=size, alpha=False)
    img.pixels = px
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return path
