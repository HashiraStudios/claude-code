"""
Visual critique loop + reference-driven modeling.

This is where agent-built models catch up to human-built ones. LLMs generate a
mesh and stop. Humans LOOK at it from several angles, judge the silhouette and
edge flow, and FIX it. These helpers make that loop mechanical:

    build -> render_turntable() -> LOOK at the PNGs -> critique() checklist -> fix -> repeat

Renders go to /mnt/user-data/outputs/ so you can open them with the file tools
and actually inspect them, not just trust that the code "should" look right.
"""

import bpy
import math
from mathutils import Vector

OUT = "/mnt/user-data/outputs"


# ---------------------------------------------------------------------------
# P4 — REFERENCE-DRIVEN MODELING
# ---------------------------------------------------------------------------

def load_reference(image_path, axis='FRONT', size=2.0, opacity=0.4):
    """Load a blueprint/reference image as a background plane you can model
    against. Model to match the reference silhouette, not from imagination.
    axis: 'FRONT' (-Y view), 'SIDE' (X view), 'TOP' (Z view)."""
    img = bpy.data.images.load(image_path, check_existing=True)
    empty = bpy.data.objects.new("REF_" + axis, None)
    empty.empty_display_type = 'IMAGE'
    empty.data = img
    empty.empty_display_size = size
    empty.use_empty_image_alpha = True
    empty.color[3] = opacity
    rot = {
        'FRONT': (math.radians(90), 0, 0),
        'SIDE':  (math.radians(90), 0, math.radians(90)),
        'TOP':   (0, 0, 0),
    }[axis]
    empty.rotation_euler = rot
    bpy.context.collection.objects.link(empty)
    return empty


def match_scale(obj, target_dim_m, along='Z'):
    """Scale an object so its size along one axis equals a real measurement,
    then APPLY scale (keeps scale 1.0 for clean export). Use to lock a model to
    a known real dimension (a 2.03 m door, a 0.10 m mug)."""
    idx = {'X': 0, 'Y': 1, 'Z': 2}[along]
    cur = obj.dimensions[idx]
    if cur <= 0:
        return
    f = target_dim_m / cur
    obj.scale = (obj.scale[0] * f, obj.scale[1] * f, obj.scale[2] * f)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


# ---------------------------------------------------------------------------
# P3 — MULTI-VIEW VISUAL CRITIQUE LOOP
# ---------------------------------------------------------------------------

def _ensure_camera():
    cam = bpy.data.objects.get("CritiqueCam")
    if cam is None:
        cam_data = bpy.data.cameras.new("CritiqueCam")
        cam = bpy.data.objects.new("CritiqueCam", cam_data)
        bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def _frame(cam, target, direction, ortho=True):
    """Point an orthographic camera at `target` from a unit `direction`."""
    bb = [target.matrix_world @ Vector(c) for c in target.bound_box]
    center = sum(bb, Vector()) / 8
    radius = max((v - center).length for v in bb)
    d = Vector(direction).normalized()
    cam.location = center + d * radius * 4
    # aim
    look = (center - cam.location).normalized()
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    cam.data.type = 'ORTHO' if ortho else 'PERSP'
    if ortho:
        cam.data.ortho_scale = radius * 2.4


def render_turntable(obj, name="critique", shading='MATCAP'):
    """Render front / right / top / 3-4 perspective views of `obj` to PNGs.
    Then OPEN the PNGs with the file-reading tools and run critique().
    shading='MATCAP' shows pure form (best for judging silhouette + topology);
    'MATERIAL' shows material/vertex colors. Uses the Workbench engine: it is
    CPU-only and headless-safe (EEVEE needs a GPU context and its enum name
    varies across Blender versions), and studio shading is the right look for
    form critique anyway."""
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    sh = scene.display.shading
    if shading == 'MATERIAL':
        sh.light = 'STUDIO'
        sh.color_type = 'MATERIAL'
    elif shading == 'TEXTURE':      # palette-atlas / textured previews
        sh.light = 'STUDIO'
        sh.color_type = 'TEXTURE'
    else:
        sh.light = 'MATCAP'
        sh.color_type = 'SINGLE'
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.film_transparent = True
    cam = _ensure_camera()

    views = {
        "front": ((0, -1, 0), True),
        "right": ((1, 0, 0), True),
        "top":   ((0, 0, 1), True),
        "persp": ((1, -1, 0.7), False),
    }
    paths = []
    for label, (direction, ortho) in views.items():
        _frame(cam, obj, direction, ortho=ortho)
        scene.render.filepath = f"{OUT}/{name}_{label}.png"
        bpy.ops.render.render(write_still=True)
        paths.append(scene.render.filepath)
    print("Rendered critique views:")
    for p in paths:
        print("  " + p)
    return paths


# ---------------------------------------------------------------------------
# CRITIQUE CHECKLIST  — run against the rendered views, honestly
# ---------------------------------------------------------------------------

CRITIQUE = """
LOOK at the rendered views before answering. Do not grade code — grade the image.

SILHOUETTE (front / side / top)
  [ ] Is the shape readable as the intended object from each ortho view?
  [ ] Are proportions correct vs the reference / real dimensions?
  [ ] Any accidental symmetry breaks, dents, or spikes?

FORM & VOLUME (perspective)
  [ ] Do the major masses read at a glance (block-out before detail)?
  [ ] Does light break where it should (bevels catching highlights)?
  [ ] Any faceting that should be a bevel, or smoothing that should be a hard edge?

TOPOLOGY (wireframe / stats via report())
  [ ] Hard-surface: bevels on all silhouette edges? support loops holding them?
  [ ] Organic: quads in deforming zones? edge loops around joints/features?
  [ ] Poles and n-gons only on flat, non-deforming areas?
  [ ] Even density where texel density must be even?

BUDGET & SCALE
  [ ] tri_count within the platform budget (see SKILL.md)?
  [ ] dimensions() match the real-world target?
  [ ] object scale == 1.0 (apply if not)?

If any box fails, FIX it and re-render. Two clean passes = done. One pass is
never enough — the second pass is what separates built from generated.
"""


def critique():
    print(CRITIQUE)


# ---------------------------------------------------------------------------
# BEAUTY RENDER — colored presentation shots (Cycles CPU, headless-safe)
# ---------------------------------------------------------------------------

def render_beauty(target, name="beauty", samples=48, sun_dir=(-0.6, 0.4, -1.0)):
    """Presentation render of the scene framed on `target`, with a sun key
    light and soft sky fill. Cycles on CPU — slower than Workbench but needs
    no GPU/GL and shows the palette material with real light. Renders two
    hero angles (3/4 left and 3/4 right)."""
    import mathutils
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.film_transparent = False

    # soft bluish sky fill
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get('Background')
    if bg:
        bg.inputs[0].default_value = (0.85, 0.90, 0.96, 1.0)
        bg.inputs[1].default_value = 0.7

    # warm sun key
    sun = bpy.data.objects.get("BeautySun")
    if sun is None:
        sun_data = bpy.data.lights.new("BeautySun", 'SUN')
        sun = bpy.data.objects.new("BeautySun", sun_data)
        bpy.context.collection.objects.link(sun)
    sun.data.energy = 3.5
    sun.data.angle = 0.2
    sun.data.color = (1.0, 0.95, 0.85)
    d = mathutils.Vector(sun_dir).normalized()
    sun.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

    cam = _ensure_camera()
    paths = []
    for label, direction in {"hero": (1, -1, 0.55), "rear": (-1, 1, 0.45)}.items():
        _frame(cam, target, direction, ortho=False)
        scene.render.filepath = f"{OUT}/{name}_{label}.png"
        bpy.ops.render.render(write_still=True)
        paths.append(scene.render.filepath)
    print("Beauty renders:")
    for p in paths:
        print("  " + p)
    return paths
