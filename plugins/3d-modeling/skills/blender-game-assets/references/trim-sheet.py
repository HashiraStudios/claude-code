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


def _strip_band(strip, margin_px=2):
    y0, y1 = STRIPS[strip]
    return (y0 + margin_px) / SIZE, (y1 - margin_px) / SIZE


def trim_map(obj, poly_indices, strip, density=1.0, margin_px=2, fit='selection'):
    """UV-map polygons onto a strip: U = world distance x density (tiles),
    V = fitted (with a bleed margin). fit='selection' spans the whole
    selection across the strip; fit='face' is HOTSPOT mode — every face
    fills the strip's full height on its own (each wall quad gets the
    complete detail, the modular-kit standard).
    Requires the piece to be axis-aligned when called — rotate the object
    AFTER mapping. Per-face dominant-axis projection:
      +-Z faces: U<-x, Vaxis<-y ; +-X faces: U<-y ; +-Y faces: U<-x."""
    uv = obj.data.uv_layers.active or obj.data.uv_layers.new(name="UVMap")
    v0, v1 = _strip_band(strip, margin_px)

    polys = [obj.data.polygons[i] for i in poly_indices]
    if not polys:
        print(f"trim_map('{strip}'): EMPTY selection — check your predicate")
        return
    spans = []
    for p in polys:
        a = max(range(3), key=lambda i: abs(p.normal[i]))
        ua, va = ((0, 1) if a == 2 else (1, 2) if a == 0 else (0, 2))
        spans.append((p, ua, va))
    # V spans PER PROJECTION AXIS — mixing them (e.g. side faces fitting by z
    # while top caps fit by y) mis-normalizes the caps onto the strip's dark
    # border rows: the "black square" end-cap artifact.
    groups = {}
    for p, ua, va in spans:
        groups.setdefault(va, []).extend(
            obj.data.vertices[vi].co[va] for vi in p.vertices)
    gspan = {va: (min(cs), (max(cs) - min(cs)) or 1.0)
             for va, cs in groups.items()}
    max_span = max(s for _, s in gspan.values())
    for p, ua, va in spans:
        mn, span = gspan[va]
        tiny = span < 0.15 * max_span      # end caps / slivers
        if fit == 'face':
            fvs = [obj.data.vertices[vi].co[va] for vi in p.vertices]
            fmn, fspan = min(fvs), (max(fvs) - min(fvs)) or 1.0
        if tiny:
            u_mean = sum(obj.data.vertices[vi].co[ua]
                         for vi in p.vertices) / len(p.vertices)
        for li, vi in zip(p.loop_indices, p.vertices):
            co = obj.data.vertices[vi].co
            if fit == 'face':
                t = (co[va] - fmn) / fspan
            else:
                t = (co[va] - mn) / span
            if tiny:
                # small caps: middle of the strip AND middle of the tile —
                # u~0 is the tiling crossfade seam, the darkest area of AI-
                # generated sources; a tiny face sampling one dark spot there
                # renders as a black square
                t = 0.35 + 0.30 * t
                u = 0.5 + (co[ua] - u_mean) * density
            else:
                u = co[ua] * density
            uv.data[li].uv = (u, v0 + t * (v1 - v0))


def trim_swap(obj, poly_indices, strip, margin_px=2):
    """ONE-CLICK DETAIL SWAP (the trim-system payoff): re-fit the current V
    of these polys into a different strip, keeping U untouched. Iterate a
    kit's details — planks -> panels -> stone — without remapping anything."""
    uv = obj.data.uv_layers.active
    v0, v1 = _strip_band(strip, margin_px)
    lis = [li for pi in poly_indices
           for li in obj.data.polygons[pi].loop_indices]
    if not lis:
        return
    vs = [uv.data[li].uv[1] for li in lis]
    mn, span = min(vs), (max(vs) - min(vs)) or 1.0
    for li in lis:
        u, v = uv.data[li].uv
        uv.data[li].uv = (u, v0 + (v - mn) / span * (v1 - v0))


def trim_map_around(obj, poly_indices, strip, density=1.0, margin_px=2,
                    axis='Z', fit='selection'):
    """BEND THE UVs: map a curved section (tower wall, arch, cone roof)
    continuously around `axis` — U accumulates along the arc in world
    units (angle x mean radius x density) so the trim flows around the
    curve without stretching; V fits the strip. Per-loop seam handling."""
    import math as _m
    uv = obj.data.uv_layers.active or obj.data.uv_layers.new(name="UVMap")
    v0, v1 = _strip_band(strip, margin_px)
    ai = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    bi, ci = (ai + 1) % 3, (ai + 2) % 3
    polys = [obj.data.polygons[i] for i in poly_indices]
    if not polys:
        print(f"trim_map_around('{strip}'): EMPTY selection — check your "
              f"band predicate against actual face-center coordinates")
        return
    rs, vcs = [], []
    for p in polys:
        for vi in p.vertices:
            co = obj.data.vertices[vi].co
            rs.append(_m.hypot(co[bi], co[ci]))
            vcs.append(co[ai])
    r_avg = sum(rs) / len(rs)
    mn, mx = min(vcs), max(vcs)
    span = (mx - mn) or 1.0
    for p in polys:
        thetas = {}
        for vi in p.vertices:
            co = obj.data.vertices[vi].co
            thetas[vi] = _m.atan2(co[ci], co[bi])
        if max(thetas.values()) - min(thetas.values()) > _m.pi:  # seam wrap
            thetas = {vi: (t + 2 * _m.pi if t < 0 else t)
                      for vi, t in thetas.items()}
        if fit == 'face':
            fvs = [obj.data.vertices[vi].co[ai] for vi in p.vertices]
            fmn, fspan = min(fvs), (max(fvs) - min(fvs)) or 1.0
        for li, vi in zip(p.loop_indices, p.vertices):
            co = obj.data.vertices[vi].co
            t = ((co[ai] - fmn) / fspan) if fit == 'face' else ((co[ai] - mn) / span)
            uv.data[li].uv = (thetas[vi] * r_avg * density, v0 + t * (v1 - v0))


# ---------------------------------------------------------------------------
# SEAM COVERS — never let two tiling materials meet raw
# ---------------------------------------------------------------------------
# Where two texture bands touch (stone course -> plaster field) or two walls
# intersect, the raw seam reads broken/dirty. The kit-design answer (heavily
# used by stylized studios): cover EVERY material transition and EVERY
# perpendicular intersection with a dedicated trim piece — a molding ring on
# a tower, an L-profile corner pillar on wall intersections, a baseboard box
# along a wall seam. The cover hides the seam AND adds style; transitions
# become features instead of defects.

def cover_ring(obj, z_local, height=0.09, outset=0.035, strip='beam',
               density=1.0, segments=18):
    """SOLID molding ring hugging `obj` (a vertical tower/cylinder, own
    local coords) at local height `z_local` — use at every texture-band
    seam. Closed rectangular profile: the inner edge SINKS INTO the wall
    (sampled radius − 0.03) so no gap can ever open against a tapered /
    bulged surface, plus top and bottom cap faces — a single offset band
    with no thickness reads as a floating paper strip, never do that.
    Radius is sampled from the mesh at both ring edges. Returns the ring."""
    import bmesh as _bm
    import math as _m
    from mathutils import Vector
    bpy.context.view_layer.update()   # matrix_world is STALE after scripted
    mesh = obj.data                   # location changes until the depsgraph
                                      # runs — without this the ring lands at
                                      # the un-offset position

    def r_at(z):
        tol, best = 0.06, []
        while not best and tol < 2.0:
            best = [_m.hypot(v.co.x, v.co.y) for v in mesh.vertices
                    if abs(v.co.z - z) < tol]
            tol *= 2
        return max(best) if best else 0.5

    rb, rt = r_at(z_local - height / 2), r_at(z_local + height / 2)
    sink = 0.03
    # profile corners per segment: inner-bottom, outer-bottom, outer-top,
    # inner-top  (inner radius buried in the wall)
    prof = ((rb - sink, -height / 2), (rb + outset, -height / 2),
            (rt + outset, height / 2), (rt - sink, height / 2))
    bm = _bm.new()
    rows = []
    for rr, zi in prof:
        rows.append([bm.verts.new((rr * _m.cos(k / segments * 2 * _m.pi),
                                   rr * _m.sin(k / segments * 2 * _m.pi), zi))
                     for k in range(segments)])
    for a, b in ((1, 2), (2, 3), (0, 1), (3, 0)):   # outer wall FIRST,
        for k in range(segments):                    # then top, bottom, inner
            k2 = (k + 1) % segments
            bm.faces.new((rows[a][k], rows[a][k2],
                          rows[b][k2], rows[b][k]))
    _bm.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(obj.name + "Ring")
    bm.to_mesh(me)
    bm.free()
    ring = bpy.data.objects.new(obj.name + "Ring", me)
    bpy.context.collection.objects.link(ring)
    ring.matrix_world = obj.matrix_world
    ring.location = obj.matrix_world @ Vector((0, 0, z_local))
    for m in obj.data.materials:
        ring.data.materials.append(m)
    # outer wall (first `segments` polys) wraps the strip normally; caps and
    # inner wall have zero z-span, so pin them to the strip's middle row
    trim_map_around(ring, list(range(segments)), strip, density=density)
    v0, v1 = _strip_band(strip)
    vmid = (v0 + v1) / 2
    uv = ring.data.uv_layers["UVMap"]
    for p in list(ring.data.polygons)[segments:]:
        ths = {vi: _m.atan2(ring.data.vertices[vi].co.y,
                            ring.data.vertices[vi].co.x) for vi in p.vertices}
        if max(ths.values()) - min(ths.values()) > _m.pi:    # seam wrap
            ths = {vi: (t + 2 * _m.pi if t < 0 else t)
                   for vi, t in ths.items()}
        for li, vi in zip(p.loop_indices, p.vertices):
            uv.data[li].uv = (ths[vi] * (rb + rt) / 2 * density, vmid)
    return ring


def cover_corner(name, height=1.0, arm=0.16, thick=0.06, location=(0, 0, 0),
                 rot_z=0.0, strip='beam', density=1.2):
    """L-profile pillar covering the OUTSIDE of two perpendicular walls'
    intersection (the corner-seam cover). Assumes the walls occupy the
    +x/+y quadrant with their OUTER faces on the x=0 and y=0 planes; the
    pillar wraps the corner edge from outside, one arm over each face
    (rotate with rot_z, then position). Map first, rotate after —
    handled internally. Returns the pillar."""
    import bmesh as _bm
    pts = [(0, 0), (0, arm), (-thick, arm), (-thick, -thick),
           (arm, -thick), (arm, 0)]
    bm = _bm.new()
    bot = [bm.verts.new((x, y, 0)) for x, y in pts]
    top = [bm.verts.new((x, y, height)) for x, y in pts]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    for k in range(len(pts)):
        k2 = (k + 1) % len(pts)
        bm.faces.new((bot[k], bot[k2], top[k2], top[k]))
    _bm.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    trim_map(ob, list(range(len(ob.data.polygons))), strip, density=density)
    ob.rotation_euler = (0, 0, rot_z)
    ob.location = location
    return ob
