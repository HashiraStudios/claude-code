"""
Trim-sheet BAKING — the real industry workflow, executable.

A drawn trim sheet is a placeholder. The professional practice (Beyond
Extent / polycount / GrabDoc workflow) is:

  1. MODEL the trim details as real high-poly 3D strips — beveled planks,
     rounded stone courses, overlapping shingles — laid flat over a 1x1 m
     plane whose UVs fill 0-1 upright.
  2. BAKE selected-to-active down to the plane: tangent NORMAL (real beveled
     edges, not luminance guesses), AO (real crevice occlusion), DIFFUSE
     color-only (per-element albedo variation for free).
  3. Texture the kit with the baked sheets; all maps share the layout.

Baking best practices encoded here:
  * extrusion ~0.05 with max_ray_distance ~2x — the smallest values that
    catch all geometry ("raise extrusion if cavities are missing, lower ray
    distance if the far side bleeds through").
  * margin_type = ADJACENT_FACES, margin 8px (kills island-edge speckles).
  * low-poly target is smooth-shaded (hard splits garble baked normals).
  * strips PERIODIC in X (elements repeat at an exact divisor of the width,
    plus one duplicate past each edge) so the sheet tiles seamlessly in U.
  * AO world distance clamped low so strips don't shadow each other.

USAGE
  parts = build_highpoly_trims()                       # 3D strip geometry
  col, nrm, ao = bake_trim_sheet(parts, size=512, out_prefix="/tmp/trim")
  colao = ao_multiply_into(col, ao, gamma=0.75)        # from pbr-maps.py
  mat = pbr_material("Kit", colao, normal_img=nrm, rough_img=...)
Strip bands match trim-sheet.py's STRIPS (y pixels /256 -> meters).
"""

import bpy
import math
import random


def _flat_mat(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*rgb, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.9
    return mat


def _hx3(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _elem(name, size, loc, mat, bevel=0.004, rot_x=0.0):
    """One beveled high-poly element (uses add_box/bevel from
    modeling-recipes.py, which must be exec'd into the same namespace)."""
    b = add_box(name, size=size, location=loc)
    if bevel > 0:
        bevel_all_sharp(b, angle_deg=40, offset=bevel, segments=2)
    if rot_x:
        b.rotation_euler = (rot_x, 0, 0)
    b.data.materials.append(mat)
    for o in bpy.data.objects:
        o.select_set(o is b)
    bpy.context.view_layer.objects.active = b
    bpy.ops.object.shade_smooth()
    return b


def build_highpoly_trims(seed=11):
    """High-poly strip geometry over the 1x1m sheet area (x,y in 0..1,
    z = relief height). Periodic in X: elements repeat at exact divisors of
    1.0 and one extra copy sits past each edge, so U tiles seamlessly."""
    rng = random.Random(seed)
    parts = []

    def jit(base, amt):
        f = 1.0 + rng.uniform(-amt, amt)
        return tuple(min(1.0, c * f) for c in base)

    # ---- stone course: y 0 .. 0.25, two offset rows of rounded blocks ----
    stone = _hx3('#8E8A82')
    period = 1 / 6
    for row in range(2):
        y0 = row * 0.125
        off = period / 2 if row % 2 else 0
        n = 0
        x = -period + off
        while x < 1.0 + period:
            m = _flat_mat(f"st{row}{n}", jit(stone, 0.10))
            parts.append(_elem("Stone", (period - 0.008, 0.117, 0.014),
                               (x + period / 2, y0 + 0.0625, 0.007), m, bevel=0.006))
            x += period
            n += 1

    # ---- plaster field: y 0.25 .. 0.5, near-flat with faint patches ----
    pl = _flat_mat("plaster", _hx3('#E6DCC8'))
    parts.append(_elem("Plaster", (1.3, 0.25, 0.006), (0.5, 0.375, 0.003),
                       pl, bevel=0.0))
    for i in range(5):
        m = _flat_mat(f"pp{i}", jit(_hx3('#E0D4BC'), 0.03))
        parts.append(_elem("Patch", (rng.uniform(0.1, 0.22), rng.uniform(0.05, 0.1), 0.002),
                           (rng.uniform(0.1, 0.9), rng.uniform(0.30, 0.45), 0.0075),
                           m, bevel=0.001))

    # ---- timber beam: y 0.5 .. 0.625, one rounded beam + notches ----
    bm = _flat_mat("beam", _hx3('#5E4630'))
    parts.append(_elem("Beam", (1.3, 0.105, 0.016), (0.5, 0.5625, 0.008),
                       bm, bevel=0.010))
    for i in range(3):
        m = _flat_mat(f"bn{i}", jit(_hx3('#4E3826'), 0.08))
        parts.append(_elem("Notch", (0.02, 0.07, 0.004),
                           ((i + 0.5) / 3, 0.5625, 0.017), m, bevel=0.002))

    # ---- planks: y 0.625 .. 0.75, 8 vertical planks with gaps ----
    period = 1 / 8
    for i in range(-1, 9):
        m = _flat_mat(f"pk{i}", jit(_hx3('#A9825B'), 0.10))
        parts.append(_elem("Plank", (period - 0.010, 0.118, 0.012),
                           ((i + 0.5) * period, 0.6875, 0.006 + rng.uniform(-0.002, 0.002)),
                           m, bevel=0.005))

    # ---- shingles: y 0.75 .. 0.875, ONE row of tilted boards ----
    # (two offset rows created a mid-band seam when a roof slab's V-fit
    # stretched the strip — the "broken middle" artifact; a single row
    # stretches cleanly across any slab)
    period = 1 / 7
    x = -period
    n = 0
    while x < 1.0 + period:
        m = _flat_mat(f"sh{n}", jit(_hx3('#7E5A44'), 0.12))
        parts.append(_elem("Shingle", (period - 0.006, 0.118, 0.008),
                           (x + period / 2, 0.8125, 0.010),
                           m, bevel=0.005, rot_x=math.radians(5)))
        x += period
        n += 1

    # ---- door planks: y 0.875 .. 1.0, tight dark planks ----
    period = 1 / 12
    for i in range(-1, 13):
        m = _flat_mat(f"dk{i}", jit(_hx3('#6E4E33'), 0.08))
        parts.append(_elem("DoorPk", (period - 0.006, 0.118, 0.010),
                           ((i + 0.5) * period, 0.9375, 0.005), m, bevel=0.004))
    return parts


BG_COLORS = {                     # what shows between elements (mortar/gaps)
    (0.0, 0.25): '#5E5A52',       # stone mortar
    (0.25, 0.5): '#D8CBB2',       # plaster undertone
    (0.5, 0.625): '#3F2E1E',      # beam shadow
    (0.625, 0.75): '#6E523A',     # plank gap
    (0.75, 0.875): '#4E362A',     # shingle underlap
    (0.875, 1.0): '#42301E',      # door gap
}


def bake_trim_sheet(parts, size=512, out_prefix=None, ao_strength=1.1,
                    handpaint=True):
    """RAYCAST bake — deterministic and headless-proof.

    Cycles' selected-to-active bake has context/CPU pitfalls in background
    builds, so this reads the geometry directly instead: one downward
    scene.ray_cast per texel gives the exact face normal (the beveled
    high-poly edges become the normal map), the hit height, and the hit
    material's base color. AO is then computed horizon-style from the height
    field (neighbors higher than you occlude you) — crevices darken exactly
    where real AO would. Returns (color, normal, ao) images."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    from mathutils import Vector

    n = size * size
    H = [0.0] * n
    npx = [0.0] * (n * 4)
    cpx = [0.0] * (n * 4)

    def bg_for(v):
        for (v0, v1), hexc in BG_COLORS.items():
            if v0 <= v < v1:
                c = hexc.lstrip('#')
                return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return (0.3, 0.3, 0.3)

    origin_z, down = 0.5, Vector((0, 0, -1))
    for y in range(size):
        v = (y + 0.5) / size
        bg = bg_for(v)
        for x in range(size):
            u = (x + 0.5) / size
            hit, loc, nrm, fi, obj, _ = scene.ray_cast(
                depsgraph, Vector((u, v, origin_z)), down, distance=1.0)
            i4 = (y * size + x) * 4
            if hit and obj.name != "TrimBakePlane":
                H[y * size + x] = loc.z
                npx[i4] = nrm.x * 0.5 + 0.5
                npx[i4 + 1] = nrm.y * 0.5 + 0.5
                npx[i4 + 2] = nrm.z * 0.5 + 0.5
                mslots = obj.material_slots
                if mslots:
                    mi = obj.data.polygons[fi].material_index if fi < len(obj.data.polygons) else 0
                    mat = mslots[min(mi, len(mslots) - 1)].material
                    bsdf = mat.node_tree.nodes.get('Principled BSDF') if mat and mat.use_nodes else None
                    rgb = tuple(bsdf.inputs['Base Color'].default_value[:3]) if bsdf else (1, 0, 1)
                else:
                    rgb = (1, 0, 1)
                cpx[i4:i4 + 3] = rgb
            else:
                npx[i4:i4 + 3] = [0.5, 0.5, 1.0]
                cpx[i4:i4 + 3] = bg
            npx[i4 + 3] = cpx[i4 + 3] = 1.0

    # ---- HANDPAINT PASS (shabik3d / WoW-school hand-painted look) --------
    # Painted surface language derived from the height field:
    #   * EDGE HIGHLIGHTS: a texel whose upper neighbor drops away is a top
    #     rim -> painted warm bright line (the signature hand-painted trick)
    #   * CONTACT SHADE: a texel whose lower neighbor drops away is a bottom
    #     rim -> painted cool darkening
    #   * GRAIN STROKES: subtle directional value streaks along U (wood)
    if handpaint:
        import math as _m
        import random as _r
        rng = _r.Random(23)
        # smooth value noise (no banding): random grid, cosine-interpolated
        gsz = 24
        grid = [[rng.uniform(-1, 1) for _ in range(gsz + 2)] for _ in range(gsz + 2)]
        def vnoise(fx, fy):
            gx, gy = fx * gsz, fy * gsz
            x0, y0 = int(gx), int(gy)
            tx, ty = gx - x0, gy - y0
            sx = (1 - _m.cos(tx * _m.pi)) / 2
            sy = (1 - _m.cos(ty * _m.pi)) / 2
            a = grid[y0][x0] * (1 - sx) + grid[y0][x0 + 1] * sx
            b = grid[y0 + 1][x0] * (1 - sx) + grid[y0 + 1][x0 + 1] * sx
            return a * (1 - sy) + b * sy
        for y in range(size):
            for x in range(size):
                idx = y * size + x
                h0 = H[idx]
                if h0 <= 0.0005:
                    continue
                i4 = idx * 4
                up = H[min(size - 1, y + 2) * size + x]
                dn = H[max(0, y - 2) * size + x]
                f = 1.0
                if h0 - up > 0.004:            # top rim -> warm highlight
                    f *= 1.28
                    cpx[i4] = min(1.0, cpx[i4] + 0.012)   # barely-warm, not pink
                elif h0 - dn > 0.004:          # bottom rim -> cool shade
                    f *= 0.80
                    cpx[i4 + 2] = min(1.0, cpx[i4 + 2] * 1.04)
                # directional grain: WOOD bands only (v >= 0.5 in our layout) —
                # smooth anisotropic noise (stretched along U), never banded sine
                if y >= size // 2:
                    f *= 1.0 + 0.05 * vnoise((x / size) * 3.0 % 1.0, (y / size) * 14.0 % 1.0)
                for c in range(3):
                    cpx[i4 + c] = max(0.0, min(1.0, cpx[i4 + c] * f))

    # horizon-based AO from the height field: taller neighbors occlude
    apx = [0.0] * (n * 4)
    texel = 1.0 / size
    radii = (2, 5, 10, 18)
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))
    for y in range(size):
        for x in range(size):
            h0 = H[y * size + x]
            occ = 0.0
            for dx, dy in dirs:
                best = 0.0
                for r in radii:
                    xx, yy = x + dx * r, y + dy * r
                    if 0 <= xx < size and 0 <= yy < size:
                        dh = H[yy * size + xx] - h0
                        if dh > 0:
                            best = max(best, dh / (dh + r * texel * 2.5))
                occ += best
            ao = max(0.0, 1.0 - ao_strength * occ / len(dirs))
            i4 = (y * size + x) * 4
            apx[i4:i4 + 3] = [ao, ao, ao]
            apx[i4 + 3] = 1.0

    def mk(name, px, noncolor):
        img = bpy.data.images.new(name, width=size, height=size, alpha=False)
        if noncolor:
            img.colorspace_settings.name = 'Non-Color'
        img.pixels = px
        if out_prefix:
            img.filepath_raw = f"{out_prefix}_{name.lower().replace('trim', '')}.png"
            img.file_format = 'PNG'
            img.save()
        return img

    col = mk("TrimColor", cpx, False)
    nrm_img = mk("TrimNormal", npx, True)
    ao_img = mk("TrimAO", apx, True)

    for o in parts:
        bpy.data.objects.remove(o, do_unlink=True)
    return col, nrm_img, ao_img
