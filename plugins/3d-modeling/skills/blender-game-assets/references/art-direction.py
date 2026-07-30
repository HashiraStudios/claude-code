"""
Art direction pass — the difference between "textured" and "painted".

A technically correct trim-sheet asset still reads STIFF when every surface
is the same value everywhere, shadows are neutral gray, and hue never moves.
Studio hand-painted work (Blizzard / Riot / WoW school) is built on four
rules this module makes executable:

  1. MACRO GRADIENT — the whole asset darkens toward the ground and lifts
     toward the top/focal point. Blizzard paints this into everything;
     an asset with uniform value from base to roof looks like plastic.
  2. SATURATED, HUE-SHIFTED SHADOWS — dark areas gain saturation and drift
     toward a cool violet, never toward gray/black. "No 100% black
     anywhere" is a hard rule of the school.
  3. WARM DODGE HIGHLIGHTS — the brightest texels drift warm (sun color)
     and slightly desaturate, like a Color Dodge pass.
  4. HUE VIBRATION — low-frequency hue drift across the surface so no two
     regions are exactly the same color (the classic "rainbow clouds on
     Hue blend" Photoshop trick). Uniform hue = mechanical.

TWO LAYERS, BOTH CHEAP:
  * stylize_grade(img)      — texture-space: rules 2/3/4 applied to the
        assembled trim sheet once, before normal/rough derivation.
  * vertex_gradient() + vertex_ao() + apply_grade(obj) — object-space:
        rule 1 plus colored contact shading, stored in a "Grade" vertex
        color attribute and MULTIPLIED over the base texture in the
        material. This rides on top of trim UVs without touching the
        mapping — the standard trick for de-uniforming trim-sheet assets
        (texture repeats, the vertex grade doesn't).

Also pair with the ART-DIRECTED PROMPT HEADER in ai-textures.py: every
material of one asset must be generated with the SAME palette sentence,
or no amount of grading will harmonize them.

Order of operations for a full asset:
    assemble_trim(...) -> stylize_grade(sheet) -> normal/rough from the
    GRADED sheet -> build objects -> vertex_gradient(obj) ->
    vertex_ao(obj) -> apply_grade(obj) -> render_beauty()
"""

import bpy
import colorsys
import math
from mathutils import Vector

GRADE_ATTR = "Grade"


# ---------------------------------------------------------------------------
# deterministic low-frequency value noise (no random module — reproducible)
# ---------------------------------------------------------------------------

def _hash01(ix, iy, seed=7):
    v = math.sin(ix * 12.9898 + iy * 78.233 + seed * 3.7) * 43758.5453
    return v - math.floor(v)


def _vnoise(x, y, cells=8, seed=7):
    """Bilinear value noise in [0,1], `cells` grid cells across the 0..1 UV."""
    fx, fy = x * cells, y * cells
    ix, iy = int(fx), int(fy)
    tx, ty = fx - ix, fy - iy
    tx = tx * tx * (3 - 2 * tx)
    ty = ty * ty * (3 - 2 * ty)
    a = _hash01(ix, iy, seed)
    b = _hash01(ix + 1, iy, seed)
    c = _hash01(ix, iy + 1, seed)
    d = _hash01(ix + 1, iy + 1, seed)
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def _hue_toward(h, target, k):
    """Shift hue toward `target` by fraction k, along the short way around."""
    delta = ((target - h + 0.5) % 1.0) - 0.5
    return (h + delta * k) % 1.0


# ---------------------------------------------------------------------------
# TEXTURE-SPACE GRADE (rules 2, 3, 4 on the assembled sheet)
# ---------------------------------------------------------------------------

def stylize_grade(img, shadow_hue=0.75, shadow_sat=0.30, shadow_shift=0.22,
                  highlight_hue=0.09, vibration=0.045, out_path=None):
    """Apply the hand-painted grade to a trim sheet (bpy image or path).
      * texels below mid value: +saturation, hue drifts toward `shadow_hue`
        (0.75 = violet) — saturated colored shadows, nothing goes gray.
      * texels above ~0.72: hue drifts warm (`highlight_hue` 0.09 = amber),
        small value dodge, slight desat — sunlit pops.
      * low-frequency hue vibration (+-`vibration`) over the whole sheet.
    Run BEFORE normal_from_image/build_rough_metal so derived maps match.
    Byte-image .pixels are sRGB-encoded; grading in display space is what a
    painter does in Photoshop, so no linearization here — by design."""
    if isinstance(img, str):
        img = bpy.data.images.load(img, check_existing=True)
    w, h = img.size
    px = list(img.pixels)
    for y in range(h):
        vy = y / h
        for x in range(w):
            i = (y * w + x) * 4
            r, g, b = px[i], px[i + 1], px[i + 2]
            hh, ss, vv = colorsys.rgb_to_hsv(r, g, b)
            # 4. hue vibration (two octaves, very low frequency)
            n = _vnoise(x / w, vy, 6, 7) * 0.7 + _vnoise(x / w, vy, 17, 31) * 0.3
            hh = (hh + (n - 0.5) * 2 * vibration) % 1.0
            # 2. saturated violet-shifted shadows
            if vv < 0.5:
                t = (0.5 - vv) / 0.5
                ss = min(1.0, ss + shadow_sat * t)
                hh = _hue_toward(hh, shadow_hue, shadow_shift * t)
                vv = max(vv, 0.06)          # no 100% black, ever
            # 3. warm dodge highlights
            if vv > 0.72:
                t = (vv - 0.72) / 0.28
                hh = _hue_toward(hh, highlight_hue, 0.30 * t)
                ss = ss * (1 - 0.18 * t)
                vv = min(1.0, vv * (1 + 0.08 * t))
            r, g, b = colorsys.hsv_to_rgb(hh, ss, vv)
            px[i], px[i + 1], px[i + 2] = r, g, b
    img.pixels = px
    if out_path:
        img.filepath_raw = out_path
        img.file_format = 'PNG'
        img.save()
    return img


# ---------------------------------------------------------------------------
# OBJECT-SPACE GRADE (rule 1 + colored contact shading, via vertex color)
# ---------------------------------------------------------------------------

def _grade_layer(mesh):
    layer = mesh.color_attributes.get(GRADE_ATTR)
    if layer is None:
        layer = mesh.color_attributes.new(GRADE_ATTR, 'FLOAT_COLOR', 'CORNER')
    return layer


def vertex_gradient(obj, bottom=(0.66, 0.60, 0.74), top=(1.07, 1.04, 0.97),
                    power=1.4):
    """Macro value gradient: multiply-tint stored per corner in the "Grade"
    attribute — saturated cool darkening at the base fading to a slight warm
    lift at the top. `power` > 1 keeps the darkening hugging the ground.
    Tints are MULTIPLIERS (top may exceed 1.0). Call before vertex_ao()."""
    mesh = obj.data
    layer = _grade_layer(mesh)
    mw = obj.matrix_world
    zs = [(mw @ v.co).z for v in mesh.vertices]
    z0, z1 = min(zs), max(zs)
    rng = max(1e-6, z1 - z0)
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            v = mesh.loops[li].vertex_index
            t = ((zs[v] - z0) / rng) ** power
            layer.data[li].color = (
                bottom[0] + (top[0] - bottom[0]) * t,
                bottom[1] + (top[1] - bottom[1]) * t,
                bottom[2] + (top[2] - bottom[2]) * t, 1.0)


def vertex_ao(obj, samples=24, dist=2.5, strength=0.85,
              tint=(0.50, 0.44, 0.62)):
    """Colored contact shading multiplied INTO the "Grade" attribute:
    hemisphere raycast occlusion per vertex, but occluded pockets darken
    toward a saturated violet `tint` instead of black (rule 2 in 3D).
    Uses scene.ray_cast, so every occluder must be linked to the scene."""
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    mesh = obj.data
    layer = _grade_layer(mesh)
    mw = obj.matrix_world
    nrm = mw.to_3x3()
    # golden-spiral hemisphere directions, tilted per-vertex to the normal
    dirs = []
    for k in range(samples):
        zz = (k + 0.5) / samples
        rr = math.sqrt(1 - zz * zz)
        th = k * 2.39996323
        dirs.append(Vector((rr * math.cos(th), rr * math.sin(th), zz)))
    occ = [0.0] * len(mesh.vertices)
    for v in mesh.vertices:
        n = (nrm @ v.normal).normalized()
        quat = Vector((0, 0, 1)).rotation_difference(n)
        origin = mw @ v.co + n * 0.02
        hits = 0
        for d in dirs:
            hit, *_ = scene.ray_cast(dg, origin, quat @ d, distance=dist)
            if hit:
                hits += 1
        occ[v.index] = hits / samples
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            o = occ[mesh.loops[li].vertex_index] * strength
            c = layer.data[li].color
            layer.data[li].color = (
                c[0] * (1 - o + o * tint[0]),
                c[1] * (1 - o + o * tint[1]),
                c[2] * (1 - o + o * tint[2]), 1.0)


def apply_grade(obj, strength=1.0):
    """Patch every material on `obj` to multiply the "Grade" vertex color
    over whatever feeds Base Color (or Emission). Trim UVs untouched —
    the texture keeps tiling, the grade varies per vertex on top of it."""
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes
                     if n.type in ('BSDF_PRINCIPLED', 'EMISSION')), None)
        if bsdf is None:
            continue
        sock = bsdf.inputs['Base Color' if bsdf.type == 'BSDF_PRINCIPLED'
                           else 'Color']
        attr = nt.nodes.new('ShaderNodeVertexColor')
        attr.layer_name = GRADE_ATTR
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = strength
        if sock.links:
            src = sock.links[0].from_socket
            nt.links.new(src, mix.inputs['A'])
        else:
            mix.inputs['A'].default_value = sock.default_value[:]
        nt.links.new(attr.outputs['Color'], mix.inputs['B'])
        nt.links.new(mix.outputs['Result'], sock)


def grade_object(obj, samples=24):
    """Convenience: full object-space pass — gradient, colored AO, patch."""
    vertex_gradient(obj)
    vertex_ao(obj, samples=samples)
    apply_grade(obj)
