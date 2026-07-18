"""
Palette-atlas texturing — the low-poly "color map" workflow, executable.

THE TECHNIQUE (Synty / Kenney style)
------------------------------------
One tiny texture (64px) shared by every prop in the scene:
  * top half  = flat color cells      -> UVs of a face COLLAPSE to the cell center
  * bottom half = vertical gradient strips -> V follows the vertex height, faking
    light/depth ("gradient trick") at zero extra geometry or texture cost
Because faces sample a single flat cell, texel density is irrelevant, seams are
invisible, and the whole scene shares ONE material = ONE draw call. Recoloring
the entire game = repainting one 64px image.

LAYOUT of the generated atlas (64x64, nearest-neighbor sampling):
  row 0 (top):    flat cells 0..3
  row 1:          flat cells 4..7
  bottom half:    4 vertical gradient strips g0..g3 (16px wide, 32px tall)

USAGE
  img  = build_palette("Forest", FLATS, GRADIENTS, path="/tmp/palette.png")
  mat  = palette_material("Forest", img)
  assign_material(obj, mat)
  paint_flat(obj, all_polys(obj), cell=2)                  # wood
  paint_gradient(obj, polys_where(obj, lambda p: ...), strip=0)  # foliage
Then render with render_turntable(obj, shading='TEXTURE') or render_beauty().
"""

import bpy


def _hex(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def build_palette(name, flats, gradients, path=None, size=64):
    """Create the palette atlas image. `flats` = up to 8 hex colors,
    `gradients` = up to 4 (top_hex, bottom_hex) pairs. Optionally save to
    `path` (PNG) so the atlas ships with the exported asset."""
    img = bpy.data.images.new(name, width=size, height=size, alpha=False)
    px = [0.0] * (size * size * 4)
    cell = size // 4          # 16px columns
    row_h = size // 8         # 16px flat rows (two rows in the top half)
    half = size // 2

    def put(x, y, rgb):
        i = (y * size + x) * 4
        px[i:i + 3] = rgb
        px[i + 3] = 1.0

    for y in range(size):
        for x in range(size):
            col = min(x // cell, 3)
            if y >= half:                       # top half: flat cells
                row = 0 if y >= size - row_h else 1
                idx = row * 4 + col
                rgb = _hex(flats[idx]) if idx < len(flats) else (1, 0, 1)
                put(x, y, rgb)
            else:                               # bottom half: gradient strips
                if col < len(gradients):
                    top, bot = _hex(gradients[col][0]), _hex(gradients[col][1])
                    t = y / (half - 1)          # 0 bottom -> 1 top of strip
                    rgb = tuple(b + (a - b) * t for a, b in zip(top, bot))
                else:
                    rgb = (1, 0, 1)
                put(x, y, rgb)

    img.pixels = px
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def palette_material(name, img):
    """One material for the whole scene. Nearest-neighbor sampling keeps flat
    cells perfectly flat; roughness high for the matte stylized look."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.interpolation = 'Closest'
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.85
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ---------------------------------------------------------------------------
# UV painting: collapse face UVs into palette cells
# ---------------------------------------------------------------------------

def _uv_layer(obj):
    uv = obj.data.uv_layers.active
    return uv if uv else obj.data.uv_layers.new(name="UVMap")


def flat_uv(cell):
    """UV center of flat cell 0..7 (row 0 = cells 0-3, row 1 = cells 4-7)."""
    col, row = cell % 4, cell // 4
    return ((col + 0.5) / 4, 0.875 if row == 0 else 0.625)


def all_polys(obj):
    return [p.index for p in obj.data.polygons]


def polys_where(obj, pred):
    """Polygon indices where pred(polygon) is true. polygon.center /
    polygon.normal are in LOCAL coordinates (lesson learned the hard way)."""
    return [p.index for p in obj.data.polygons if pred(p)]


def paint_flat(obj, poly_indices, cell):
    """Collapse the UVs of the given polygons onto a flat color cell."""
    uv = _uv_layer(obj)
    target = flat_uv(cell)
    for pi in poly_indices:
        for li in obj.data.polygons[pi].loop_indices:
            uv.data[li].uv = target


def paint_gradient(obj, poly_indices, strip, axis='Z', lo=None, hi=None):
    """Map the given polygons into gradient strip 0..3: each vertex's V follows
    its height (or another axis), so the face shades smoothly top-to-bottom.
    The classic low-poly 'fake lighting' trick. lo/hi override the auto range
    (local coordinates)."""
    uv = _uv_layer(obj)
    ai = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    u = (strip % 4 + 0.5) / 4
    coords = [obj.data.vertices[v].co[ai]
              for pi in poly_indices for v in obj.data.polygons[pi].vertices]
    if not coords:
        return
    mn = lo if lo is not None else min(coords)
    mx = hi if hi is not None else max(coords)
    span = (mx - mn) or 1.0
    for pi in poly_indices:
        poly = obj.data.polygons[pi]
        for li, vi in zip(poly.loop_indices, poly.vertices):
            t = (obj.data.vertices[vi].co[ai] - mn) / span
            t = max(0.0, min(1.0, t))
            uv.data[li].uv = (u, 0.03 + t * 0.44)   # stay inside the strip
