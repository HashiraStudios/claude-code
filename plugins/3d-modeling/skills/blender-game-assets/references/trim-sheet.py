"""
Trim-sheet texturing — modular architecture on ONE texture, executable.

THE TECHNIQUE
-------------
A trim sheet is a single texture organized as HORIZONTAL STRIPS of tiling
surface detail (stone course, plaster, wood beam, planks, shingles...).
Geometry UV-maps onto a strip: U tiles freely along the strip (infinite
horizontal repeat), V is FITTED to the strip's height (never tiles).
One sheet textures an entire modular building kit -> one material, one draw
call, and kit pieces snap together with perfectly matching texel density.

Rules that make trims work (Beyond Extent / polycount practice):
  * U direction = the tiling direction. Rotate islands in 90° steps to align.
  * V is fitted, with a 2px margin inside the strip (mip/filter bleed guard).
  * Strip heights should correspond to real-world sizes (e.g. 64px = 0.5 m
    at 128px/m) so density stays consistent across the kit.
  * Big uniform strips (plaster) carry walls; narrow strips (beams, moldings)
    carry the borders and silhouette lines.
  * Keep pieces axis-aligned while mapping; rotate the OBJECT afterwards
    (object transforms don't touch UVs) — e.g. roof slabs.

USAGE
  img = build_trim_sheet("Cottage", path="/tmp/trim.png")
  mat = trim_material("Cottage", img)      # then assign_material(obj, mat)
  trim_map(obj, all_polys(obj), 'plaster', density=0.7)
  trim_map(beam, all_polys(beam), 'beam')
Uses all_polys / polys_where / assign_material from palette-texturing.py.
"""

import bpy
import random

SIZE = 256
# strip name -> (y0, y1) pixel rows, bottom-up. Edit freely per project.
STRIPS = {
    'stone':    (0, 64),      # foundation course, 2 block rows
    'plaster':  (64, 128),    # big uniform wall field
    'beam':     (128, 160),   # dark timber, horizontal grain
    'planks':   (160, 192),   # light planks, vertical joints
    'shingles': (192, 224),   # roof rows
    'door':     (224, 256),   # dark planks, tight joints
}


def _hx(c):
    c = c.lstrip('#')
    return [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def build_trim_sheet(name, path=None, seed=7):
    """Procedurally paint a stylized 256px trim sheet (see STRIPS layout)."""
    rng = random.Random(seed)
    px = [0.0] * (SIZE * SIZE * 4)

    def put(x, y, rgb):
        i = (y * SIZE + x) * 4
        px[i:i + 3] = rgb
        px[i + 3] = 1.0

    def shade(rgb, f):
        return [max(0.0, min(1.0, c * f)) for c in rgb]

    def fill(y0, y1, rgb, jitter=0.0):
        for y in range(y0, y1):
            for x in range(SIZE):
                f = 1.0 + rng.uniform(-jitter, jitter)
                put(x, y, shade(rgb, f))

    def hline(y, rgb, h=1):
        for yy in range(y, min(y + h, SIZE)):
            for x in range(SIZE):
                put(x, yy, rgb)

    # stone: two offset block rows with mortar + per-block value
    base = _hx('#8E8A82'); mortar = _hx('#66625B')
    fill(0, 64, base)
    for row, (ry0, ry1) in enumerate([(0, 32), (32, 64)]):
        off = 20 if row % 2 else 0
        for bx0 in range(-off, SIZE + 1, 42):
            bf = 1.0 + rng.uniform(-0.09, 0.09)
            for y in range(ry0 + 2, ry1 - 1):
                for x in range(max(0, bx0 + 2), min(SIZE, bx0 + 40)):
                    put(x, y, shade(base, bf * (1.06 if y >= ry1 - 5 else 1.0)))
            for y in range(ry0, ry0 + 2):
                for x in range(max(0, bx0), min(SIZE, bx0 + 42)):
                    put(x, y, mortar)
            for y in range(ry0, ry1):
                for x in range(bx0, bx0 + 2):
                    if 0 <= x < SIZE:
                        put(x, y, mortar)

    # plaster: warm field, light noise, shadow line at its base
    fill(64, 128, _hx('#E6DCC8'), jitter=0.015)
    hline(64, _hx('#C9BCA4'), 3)

    # beam: dark timber, horizontal grain streaks, edge highlight/shadow
    fill(128, 160, _hx('#5E4630'), jitter=0.02)
    for _ in range(26):
        y = rng.randrange(131, 157)
        x0 = rng.randrange(0, SIZE)
        ln = rng.randrange(30, 90)
        g = shade(_hx('#5E4630'), rng.uniform(0.78, 0.9))
        for x in range(x0, x0 + ln):
            put(x % SIZE, y, g)
    hline(157, _hx('#7A5C40'), 2)
    hline(128, _hx('#3F2E1E'), 2)

    # planks: light wood, vertical joints, sparse grain
    fill(160, 192, _hx('#A9825B'), jitter=0.02)
    for x0 in range(0, SIZE, 21):
        for y in range(160, 192):
            put(x0 % SIZE, y, _hx('#7A5A3C'))
            put((x0 + 1) % SIZE, y, _hx('#8A6644'))
    hline(189, shade(_hx('#A9825B'), 1.08), 2)

    # shingles: two offset rows with drop shadow under each course
    fill(192, 224, _hx('#7E5A44'), jitter=0.025)
    for row, (ry0, ry1) in enumerate([(192, 208), (208, 224)]):
        hline(ry0, _hx('#4E362A'), 3)
        off = 12 if row % 2 else 0
        for x0 in range(-off, SIZE + 1, 24):
            for y in range(ry0 + 3, ry1):
                if 0 <= x0 < SIZE:
                    put(x0, y, _hx('#5E4231'))
    hline(221, shade(_hx('#7E5A44'), 1.1), 2)

    # door: dark tight planks
    fill(224, 256, _hx('#6E4E33'), jitter=0.02)
    for x0 in range(0, SIZE, 16):
        for y in range(224, 256):
            put(x0, y, _hx('#4A3320'))
    hline(253, shade(_hx('#6E4E33'), 1.1), 2)

    img = bpy.data.images.new(name, width=SIZE, height=SIZE, alpha=False)
    img.pixels = px
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def trim_material(name, img):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Linear'
    tex.extension = 'REPEAT'
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.9
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def trim_map(obj, poly_indices, strip, density=1.0, margin_px=2):
    """UV-map polygons onto a strip: U = world distance x density (tiles),
    V = fitted across the selection's span (with a bleed margin).
    Requires the piece to be axis-aligned when called — rotate the object
    AFTER mapping. Per-face dominant-axis projection:
      +-Z faces: U<-x, Vaxis<-y ; +-X faces: U<-y ; +-Y faces: U<-x."""
    uv = obj.data.uv_layers.active or obj.data.uv_layers.new(name="UVMap")
    y0, y1 = STRIPS[strip]
    v0, v1 = (y0 + margin_px) / SIZE, (y1 - margin_px) / SIZE

    polys = [obj.data.polygons[i] for i in poly_indices]
    spans = []
    for p in polys:
        a = max(range(3), key=lambda i: abs(p.normal[i]))
        ua, va = ((0, 1) if a == 2 else (1, 2) if a == 0 else (0, 2))
        spans.append((p, ua, va))
    vcoords = [obj.data.vertices[vi].co[va]
               for p, ua, va in spans for vi in p.vertices]
    mn, mx = min(vcoords), max(vcoords)
    span = (mx - mn) or 1.0
    for p, ua, va in spans:
        for li, vi in zip(p.loop_indices, p.vertices):
            co = obj.data.vertices[vi].co
            t = (co[va] - mn) / span
            uv.data[li].uv = (co[ua] * density, v0 + t * (v1 - v0))
