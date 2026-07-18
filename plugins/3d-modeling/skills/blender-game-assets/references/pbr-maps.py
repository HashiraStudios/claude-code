"""
PBR map generation — normal / AO / roughness / metallic, executable.

Two complementary routes, both engine-ready:

A) PROCEDURAL SYNTHESIS (for trim sheets / atlases)
   - normal_from_image(): height-from-luminance + Sobel -> tangent-space
     normal map. Works on our procedural sheets because joints/mortar/grain
     are drawn darker = deeper (classic quick-derive; for arbitrary photo
     textures prefer a real height source).
   - build_rough_metal(): per-strip roughness/metallic sheets matching the
     trim-sheet STRIPS layout (metal strips -> metallic 1 / low rough, etc).
   Result: color + normal + roughness + metallic that share ONE UV layout.

B) CYCLES BAKES (from real geometry, headless-CPU safe)
   - bake_ao(): ambient occlusion into the object's UVs. Multiply into base
     color for mobile (ao_multiply_into) or ship as its own map.
   - bake_bevel_normal(): THE pro trick — a Bevel shader node piped into the
     Normal input, baked to a tangent normal map: rounded highlight-catching
     edges on a HARD low-poly mesh, zero extra triangles.

Wiring: pbr_material() hooks all maps into a Principled BSDF
(color sRGB; rough/metal/normal Non-Color; NormalMap node for the normal).

Bake notes (Blender 4.x): bakes write to the ACTIVE image texture node of
each material on the object — the helpers create/select it for you. CPU
Cycles, 16-32 samples is plenty for AO/bevel bakes at 512px.
"""

import bpy
import math


# ---------------------------------------------------------------------------
# A) PROCEDURAL SYNTHESIS
# ---------------------------------------------------------------------------

def _lum(px, i):
    return 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]


def normal_from_image(src_img, name="Normal", strength=2.0, path=None):
    """Tangent-space normal map from an image's luminance (Sobel gradients).
    `strength` scales bumpiness. Dark lines read as grooves."""
    w, h = src_img.size
    sp = list(src_img.pixels)
    H = [_lum(sp, (y * w + x) * 4) for y in range(h) for x in range(w)]

    def hv(x, y):
        return H[(y % h) * w + (x % w)]

    out = [0.0] * (w * h * 4)
    for y in range(h):
        for x in range(w):
            gx = (hv(x + 1, y - 1) + 2 * hv(x + 1, y) + hv(x + 1, y + 1)
                  - hv(x - 1, y - 1) - 2 * hv(x - 1, y) - hv(x - 1, y + 1))
            gy = (hv(x - 1, y + 1) + 2 * hv(x, y + 1) + hv(x + 1, y + 1)
                  - hv(x - 1, y - 1) - 2 * hv(x, y - 1) - hv(x + 1, y - 1))
            nx, ny, nz = -gx * strength, -gy * strength, 1.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            i = (y * w + x) * 4
            out[i] = nx / ln * 0.5 + 0.5
            out[i + 1] = ny / ln * 0.5 + 0.5
            out[i + 2] = nz / ln * 0.5 + 0.5
            out[i + 3] = 1.0
    img = bpy.data.images.new(name, width=w, height=h, alpha=False)
    img.colorspace_settings.name = 'Non-Color'
    img.pixels = out
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def build_rough_metal(strips_rm, name="RM", size=256, strips=None, path_rough=None,
                      path_metal=None):
    """Per-strip roughness & metallic sheets matching trim-sheet layout.
    `strips_rm` = {strip_name: (roughness, metallic)}; `strips` = the STRIPS
    dict from trim-sheet.py (y0, y1 pixel rows). Returns (rough_img, metal_img).
    Typical values: wood (0.85, 0) · plaster (0.9, 0) · stone (0.95, 0) ·
    iron (0.45, 1.0) · gold (0.35, 1.0) · ceramic glaze (0.25, 0)."""
    rough = [0.0] * (size * size * 4)
    metal = [0.0] * (size * size * 4)
    for sname, (y0, y1) in (strips or {}).items():
        r, m = strips_rm.get(sname, (0.8, 0.0))
        for y in range(y0, y1):
            for x in range(size):
                i = (y * size + x) * 4
                rough[i:i + 3] = [r, r, r]
                rough[i + 3] = 1.0
                metal[i:i + 3] = [m, m, m]
                metal[i + 3] = 1.0
    ri = bpy.data.images.new(name + "_rough", width=size, height=size, alpha=False)
    mi = bpy.data.images.new(name + "_metal", width=size, height=size, alpha=False)
    ri.colorspace_settings.name = 'Non-Color'
    mi.colorspace_settings.name = 'Non-Color'
    ri.pixels = rough
    mi.pixels = metal
    for img, p in ((ri, path_rough), (mi, path_metal)):
        if p:
            img.filepath_raw = p
            img.file_format = 'PNG'
            img.save()
    return ri, mi


def pbr_material(name, color_img, normal_img=None, rough_img=None,
                 metal_img=None, normal_strength=1.0):
    """Principled material wired with the full map set. Color is sRGB;
    everything else Non-Color (set on the images by the builders above)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

    def tex(img):
        t = nodes.new('ShaderNodeTexImage')
        t.image = img
        t.interpolation = 'Linear'
        return t

    links.new(tex(color_img).outputs['Color'], bsdf.inputs['Base Color'])
    if rough_img:
        links.new(tex(rough_img).outputs['Color'], bsdf.inputs['Roughness'])
    if metal_img:
        links.new(tex(metal_img).outputs['Color'], bsdf.inputs['Metallic'])
    if normal_img:
        nm = nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = normal_strength
        links.new(tex(normal_img).outputs['Color'], nm.inputs['Color'])
        links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


# ---------------------------------------------------------------------------
# B) CYCLES BAKES
# ---------------------------------------------------------------------------

def _bake_target(obj, name, size):
    """Create the bake image and make it the ACTIVE image node in every
    material slot on the object (bakes write to the active node)."""
    img = bpy.data.images.new(name, width=size, height=size, alpha=False)
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        node = mat.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = img
        mat.node_tree.nodes.active = node
        node.select = True
    return img


def _bake_setup(samples):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.render.bake.margin = 4


def bake_ao(obj, size=512, samples=32, path=None):
    """Bake ambient occlusion into the object's UV layout. Requires unwrapped,
    non-overlapping-enough UVs (overlapped symmetric islands will share AO)."""
    _bake_setup(samples)
    img = _bake_target(obj, obj.name + "_AO", size)
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='AO')
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def bake_bevel_normal(obj, radius=0.015, bevel_samples=8, size=512,
                      samples=16, path=None):
    """Rounded-edge normal map from a HARD mesh: temporarily pipes a Bevel
    node into every material's Normal input, bakes tangent normals, then
    removes the temp nodes. Apply the result via pbr_material — soft
    highlight-catching edges at zero triangle cost."""
    _bake_setup(samples)
    temp = []
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf:
            continue
        bv = nt.nodes.new('ShaderNodeBevel')
        bv.inputs['Radius'].default_value = radius
        bv.samples = bevel_samples
        lk = nt.links.new(bv.outputs['Normal'], bsdf.inputs['Normal'])
        temp.append((nt, bv, lk))
    img = _bake_target(obj, obj.name + "_BevelNrm", size)
    img.colorspace_settings.name = 'Non-Color'
    for o in bpy.data.objects:
        o.select_set(o is obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='NORMAL')
    for nt, bv, lk in temp:
        nt.links.remove(lk)
        nt.nodes.remove(bv)
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img


def ao_multiply_into(color_img, ao_img, name="ColorAO", gamma=1.0, path=None):
    """Mobile trick: pre-multiply AO into the base color so the engine pays
    for one sampler. gamma<1 softens the darkening. Both images must share
    the same UV layout and size."""
    w, h = color_img.size
    cp, ap = list(color_img.pixels), list(ao_img.pixels)
    out = [0.0] * (w * h * 4)
    for i in range(0, w * h * 4, 4):
        ao = _lum(ap, i) ** gamma
        out[i] = cp[i] * ao
        out[i + 1] = cp[i + 1] * ao
        out[i + 2] = cp[i + 2] * ao
        out[i + 3] = 1.0
    img = bpy.data.images.new(name, width=w, height=h, alpha=False)
    img.pixels = out
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img
