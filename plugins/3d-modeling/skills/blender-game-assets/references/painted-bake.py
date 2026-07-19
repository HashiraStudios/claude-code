"""
Painted bake — the Supercell/mobile character texture look, executable.

THE RESEARCH (Supercell Creature Shop / Airborn Studios / mobile practice)
--------------------------------------------------------------------------
Supercell-grade characters are concept -> sculpt -> retopo -> and then the
step our pipeline was missing: the FINAL TEXTURE pass, where ALL lighting
is painted/baked into the diffuse:
  * high-poly AO multiplied over the albedo,
  * a vertical light-to-dark gradient multiplied on top,
  * directional (top-front) lighting with a WARM light / COOL shadow hue
    shift painted in,
  * specular highlights drawn into the diffuse on up-facing surfaces.
The shipped character is effectively unlit — the texture IS the lighting.
That is why raw-albedo characters read "plastic" next to Brawl Stars ones.

THE EXECUTABLE ADAPTATION
-------------------------
painted_bake(obj, palette_img) does the whole pass headless:
  1. adds a unique second UV set ('BakeUV' via smart_project) alongside the
     palette UVs,
  2. self-bakes (the Cycles path that works headless): albedo (DIFFUSE
     color-only, reading the palette through a UVMap node), AO, and
     OBJECT-space normals into the unique layout,
  3. composes the painted diffuse in Python per texel:
       albedo x AO^g x heightGradient x (warmLight..coolShadow by N.L)
       + painted spec on up-facing lit texels,
  4. returns a single-texture, high-roughness material — the mobile
     diffuse-only character look.
"""

import bpy
import math
from mathutils import Vector


def _self_bake(obj, btype, size, name, noncolor, extra=None, samples=None):
    if samples:
        bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new(name, width=size, height=size, alpha=False)
    if noncolor:
        img.colorspace_settings.name = 'Non-Color'
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = img
        mat.node_tree.nodes.active = node
        node.select = True
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    kwargs = dict(type=btype, margin=8)
    if extra:
        kwargs.update(extra)
    bpy.ops.object.bake(**kwargs)
    return img


def painted_bake(obj, palette_img, size=512, samples=32,
                 light_dir=(0.5, -0.42, 0.76),   # MATCH the render rig's key sun
                 warm=(1.06, 1.0, 0.92), cool=(0.78, 0.84, 1.02),
                 ao_gamma=0.75, grad_amount=0.16, spec_amount=0.35,
                 path=None):
    """Bake the hand-painted-look diffuse for `obj` (palette-UV'd on layer
    'UVMap'). Returns the final single-texture material."""
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples

    # 1. unique bake UVs on a second layer
    if 'BakeUV' not in obj.data.uv_layers:
        obj.data.uv_layers.new(name='BakeUV')
    obj.data.uv_layers.active = obj.data.uv_layers['BakeUV']
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 2. material that reads the palette through the FIRST UV layer,
    #    so DIFFUSE bakes resolve colors while we bake into the second
    mat = bpy.data.materials.new("PaintedSrc")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    uvn = nodes.new('ShaderNodeUVMap')
    uvn.uv_map = 'UVMap'
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = palette_img
    # 'Closest': collapsed-point UVs have a degenerate filter footprint —
    # Linear/EWA would average the whole palette into every sample
    tex.interpolation = 'Closest'
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(uvn.outputs['UV'], tex.inputs['Vector'])
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    # albedo: rasterized in Python, NOT baked — bake AA averages neighboring
    # palette cells at triangle borders into speckle; rasterizing each loop-
    # triangle with its face's exact cell color is deterministic and clean
    pw, ph = palette_img.size
    ppx = list(palette_img.pixels)
    uv_pal = obj.data.uv_layers['UVMap']
    uv_bake = obj.data.uv_layers['BakeUV']
    obj.data.calc_loop_triangles()
    A = [0.0] * (size * size * 4)
    for tri in obj.data.loop_triangles:
        lu, lv = uv_pal.data[tri.loops[0]].uv
        px_, py_ = min(pw - 1, int(lu * pw)), min(ph - 1, int(lv * ph))
        pi = (py_ * pw + px_) * 4
        col = ppx[pi:pi + 3]
        pts = [uv_bake.data[l].uv for l in tri.loops]
        xs = [p[0] * size for p in pts]
        ys = [p[1] * size for p in pts]
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
                if w0 >= -0.10 and w1 >= -0.10 and (1 - w0 - w1) >= -0.10:  # ~1px outset kills seam gutters
                    i4 = (yy * size + xx) * 4
                    A[i4:i4 + 3] = col
                    A[i4 + 3] = 1.0

    ao = _self_bake(obj, 'AO', size, "PB_ao", True, samples=128)
    nrm = _self_bake(obj, 'NORMAL', size, "PB_nrm", True,
                     extra={'normal_space': 'OBJECT'})
    pos = _self_bake(obj, 'POSITION', size, "PB_pos", True)

    # 3. compose the painted diffuse
    O, N, P = (list(i.pixels) for i in (ao, nrm, pos))

    def lin(v):
        # byte-backed sRGB images store sRGB-encoded values in .pixels —
        # decode to linear before compositing (then re-encode at the end)
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    A = [lin(v) if (j % 4) != 3 else v for j, v in enumerate(A)]
    # 3x3 mean blur on AO to kill bake sampling noise
    Ob = O[:]
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            i4 = (y * size + x) * 4
            s = 0.0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    s += O[((y + dy) * size + (x + dx)) * 4]
            Ob[i4] = s / 9.0
    O = Ob
    L = Vector(light_dir).normalized()
    zs = [P[i + 2] for i in range(0, len(P), 4) if P[i + 3] > 0]
    zmin, zmax = (min(zs), max(zs)) if zs else (0, 1)
    zspan = (zmax - zmin) or 1.0
    def srgb(v):
        # Cycles bakes LINEAR values; the output image is interpreted as
        # sRGB content — encode, or every color desaturates/hue-shifts.
        v = max(0.0, min(1.0, v))
        return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055

    outpx = [0.0] * (size * size * 4)
    for i in range(0, size * size * 4, 4):
        n = Vector((N[i] * 2 - 1, N[i + 1] * 2 - 1, N[i + 2] * 2 - 1))
        if n.length < 0.35:                      # empty texel
            outpx[i:i + 3] = [srgb(A[i]), srgb(A[i + 1]), srgb(A[i + 2])]
            outpx[i + 3] = 1.0
            continue
        n.normalize()
        lam = max(0.0, n.dot(L))
        # gentle: the bake carries AO/gradient/hue-shift, scene lights do the rest
        f = 0.58 + 0.47 * lam
        tint = [cool[c] + (warm[c] - cool[c]) * f for c in range(3)]
        aof = max(0.0, min(1.0, O[i])) ** ao_gamma
        hgt = 1.0 - grad_amount + grad_amount * ((P[i + 2] - zmin) / zspan)
        spec = spec_amount * (lam ** 10) * max(0.0, n.z)
        for c in range(3):
            v = A[i + c] * tint[c] * f * aof * hgt / 0.95 + spec
            outpx[i + c] = srgb(v)
        outpx[i + 3] = 1.0

    painted = bpy.data.images.new("PaintedDiffuse", width=size, height=size,
                                  alpha=False)
    painted.pixels = outpx
    if path:
        painted.filepath_raw = path
        painted.file_format = 'PNG'
        painted.save()

    # 4. final diffuse-only material bound to BakeUV
    fmat = bpy.data.materials.new("Painted")
    fmat.use_nodes = True
    nodes, links = fmat.node_tree.nodes, fmat.node_tree.links
    nodes.clear()
    uvn = nodes.new('ShaderNodeUVMap')
    uvn.uv_map = 'BakeUV'
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = painted
    tex.interpolation = 'Linear'
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.95
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(uvn.outputs['UV'], tex.inputs['Vector'])
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    obj.data.materials.clear()
    obj.data.materials.append(fmat)
    return fmat
