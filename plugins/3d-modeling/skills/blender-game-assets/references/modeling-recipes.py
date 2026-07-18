"""
Executable modeling recipes for agent-driven Blender modeling.

WHY THIS FILE EXISTS
--------------------
An agent does NOT press Ctrl+R / E / B. It constructs geometry by running
Python. Every recipe below is a real, parameterized operation you can paste
into `blender:execute_blender_code(code)`. Prefer these over describing hotkeys.

Two layers are provided:
  1. bmesh.ops  -> deterministic, headless-safe, numeric. USE THIS BY DEFAULT.
  2. bpy.ops    -> only where bmesh has no equivalent (modifiers, some tools),
                   always with explicit numeric parameters, never "the user will
                   drag the mouse".

CONVENTIONS
  * Distances are in Blender units = meters (see references/goal-to-technique.md
    for real-scale setup). Pass real measurements, not eyeballed guesses.
  * Angles are radians. Use math.radians(deg).
  * Every recipe leaves the mesh with consistent normals and no stray doubles
    unless noted. Call `cleanup(obj)` after a construction session.

USAGE PATTERN
  obj = active_or_new("Crate")
  bm  = edit_begin(obj)
  ... bmesh.ops on bm ...
  edit_commit(bm, obj)
  cleanup(obj)
"""

import bpy
import bmesh
import math
from mathutils import Vector, Matrix


# ---------------------------------------------------------------------------
# bmesh session helpers  (open once, batch ops, write once -> fast + clean)
# ---------------------------------------------------------------------------

def active_or_new(name):
    """Return the active object, or create an empty mesh object named `name`."""
    obj = bpy.context.active_object
    if obj and obj.type == 'MESH':
        return obj
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def edit_begin(obj):
    """Get a bmesh from an object's mesh (object mode). Returns bm."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    return bm


def edit_commit(bm, obj):
    """Write bmesh back to the object's mesh and free it."""
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def cleanup(obj, merge_dist=1e-4):
    """Merge doubles + recalc normals. Run after any construction session."""
    bm = edit_begin(obj)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    edit_commit(bm, obj)


# ---------------------------------------------------------------------------
# PRIMITIVES  (start blocky, refine later — see block-out method in SKILL.md)
# ---------------------------------------------------------------------------

def add_box(name, size=(1, 1, 1), location=(0, 0, 0)):
    """A box with independent X/Y/Z dimensions in meters. Better than a
    unit cube you then scale, because scale stays 1.0 (no export headaches)."""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    obj.location = location
    bpy.context.view_layer.objects.active = obj
    return obj


def add_cylinder(name, radius=0.5, depth=1.0, segments=16, cap=True, location=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=cap, cap_tris=False, segments=segments,
        radius1=radius, radius2=radius, depth=depth,
    )
    bm.to_mesh(mesh)
    bm.free()
    obj.location = location
    bpy.context.view_layer.objects.active = obj
    return obj


# ---------------------------------------------------------------------------
# CORE EDIT OPERATIONS  (the real equivalents of the hotkeys)
# ---------------------------------------------------------------------------

def faces_by_normal(bm, axis='Z', sign=1, tol=0.5):
    """Select faces whose normal points roughly along +/-axis.
    Handy for 'extrude the top', 'inset the front', etc."""
    idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    out = []
    for f in bm.faces:
        if math.copysign(1, f.normal[idx]) == sign and abs(f.normal[idx]) > tol:
            out.append(f)
    return out


def extrude_faces(bm, faces, translate):
    """E-key equivalent, but exact. Extrude `faces` and move the new geometry
    by `translate` (a 3-tuple in meters). Returns the new faces."""
    res = bmesh.ops.extrude_face_region(bm, geom=faces)
    new_geom = res['geom']
    new_verts = [g for g in new_geom if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=new_verts, vec=Vector(translate))
    return [g for g in new_geom if isinstance(g, bmesh.types.BMFace)]


def extrude_along_normal(bm, faces, distance):
    """Extrude each face outward along its own normal by `distance` meters.
    Use for panels, greebles, thickness on a single face."""
    res = bmesh.ops.extrude_face_region(bm, geom=faces)
    new_geom = res['geom']
    new_faces = [g for g in new_geom if isinstance(g, bmesh.types.BMFace)]
    new_verts = [g for g in new_geom if isinstance(g, bmesh.types.BMVert)]
    if new_faces:
        n = new_faces[0].normal.copy()
        bmesh.ops.translate(bm, verts=new_verts, vec=n * distance)
    return new_faces


def inset_faces(bm, faces, thickness=0.05, depth=0.0, individual=False):
    """I-key equivalent. `thickness` shrinks the face inward (meters);
    `depth` pushes it in/out along the normal. Great for buttons, panels,
    window frames. individual=True insets each face separately."""
    if individual:
        res = bmesh.ops.inset_individual(bm, faces=faces, thickness=thickness, depth=depth)
    else:
        res = bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=depth, use_boundary=True)
    return res.get('faces', [])


def bevel_edges(bm, edges, offset=0.02, segments=2, profile=0.5, clamp=True):
    """Ctrl+B equivalent. Rounds `edges` by `offset` meters over `segments`.
    segments=1 = chamfer; 2-3 = subtle round for hard-surface; profile 0.5 =
    circular, <0.5 concave, >0.5 bulge. This is how you get readable silhouettes
    on low-poly without subdivision."""
    res = bmesh.ops.bevel(
        bm, geom=edges, offset=offset, offset_type='OFFSET',
        segments=segments, profile=profile, affect='EDGES',
        clamp_overlap=clamp,
    )
    return res.get('faces', [])


def bevel_all_sharp(obj, angle_deg=40, offset=0.02, segments=2):
    """Convenience: bevel every edge sharper than `angle_deg`. The single most
    impactful low-poly move — it catches highlights so a 300-tri prop reads
    as solid, not faceted."""
    bm = edit_begin(obj)
    sharp = [e for e in bm.edges if e.calc_face_angle(None) is not None
             and e.calc_face_angle(0.0) > math.radians(angle_deg)]
    bmesh.ops.bevel(bm, geom=sharp, offset=offset, offset_type='OFFSET',
                    segments=segments, profile=0.7, affect='EDGES', clamp_overlap=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    edit_commit(bm, obj)


def loop_cut(bm, faces, cuts=1):
    """Ctrl+R equivalent via subdivision. Adds `cuts` evenly spaced loops
    across the given faces' edges. For a clean single ring, pass the faces of
    one 'tube' section. use_grid_fill keeps quads."""
    edges = set()
    for f in faces:
        for e in f.edges:
            edges.add(e)
    res = bmesh.ops.subdivide_edges(
        bm, edges=list(edges), cuts=cuts, use_grid_fill=True,
    )
    return res


def bridge(bm, edge_loops):
    """Bridge Edge Loops. `edge_loops` = list of boundary edges from two open
    loops; fills the tube between them. Use to connect two profiles (e.g. a
    handle, a pipe joint)."""
    return bmesh.ops.bridge_loops(bm, edges=edge_loops)


def spin_lathe(bm, profile_verts, axis=(0, 0, 1), center=(0, 0, 0),
               angle_deg=360, steps=24):
    """Lathe / revolve — the fastest way to make bottles, cups, columns,
    wheels, vases. Draw a profile (a chain of verts in the XZ plane), then spin
    it around `axis`. `steps` controls roundness."""
    geom = list(profile_verts) + [e for v in profile_verts for e in v.link_edges]
    bmesh.ops.spin(
        bm, geom=geom, cent=Vector(center), axis=Vector(axis),
        dvec=Vector((0, 0, 0)), angle=math.radians(angle_deg),
        steps=steps, use_merge=(angle_deg >= 360),
    )


def subdivide_smooth(bm, faces=None, cuts=1, smooth=1.0):
    """Add resolution AND round it (Subdivide with smoothing). Use sparingly on
    game assets — for organic curvature where a bevel won't do."""
    edges = list(bm.edges) if faces is None else list({e for f in faces for e in f.edges})
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=cuts, use_grid_fill=True, smooth=smooth)


# ---------------------------------------------------------------------------
# NON-DESTRUCTIVE MODIFIERS  (fast symmetry / repetition / thickness)
# ---------------------------------------------------------------------------

def add_mirror(obj, axis=('X',), use_bisect=True, merge=0.001):
    """Model one half, mirror the rest. Always model on the +axis side and let
    Mirror build the other. Keep it live until the silhouette is approved."""
    m = obj.modifiers.new('Mirror', 'MIRROR')
    m.use_axis = tuple(a in axis for a in ('X', 'Y', 'Z'))
    if use_bisect:
        m.use_bisect_axis = m.use_axis
    m.use_clip = True
    m.merge_threshold = merge
    return m


def add_array(obj, count=3, offset=(1.0, 0, 0), relative=False):
    """Fences, stairs, windows, chain links. `offset` in meters (absolute) or
    factors of the bounding box (relative=True)."""
    m = obj.modifiers.new('Array', 'ARRAY')
    m.count = count
    m.use_relative_offset = relative
    m.use_constant_offset = not relative
    if relative:
        m.relative_offset_displace = offset
    else:
        m.constant_offset_displace = offset
    return m


def add_solidify(obj, thickness=0.02, even=True):
    """Give a single-sided surface real thickness (walls, blades, leaves,
    sheet metal). Cheaper and cleaner than extruding by hand."""
    m = obj.modifiers.new('Solidify', 'SOLIDIFY')
    m.thickness = thickness
    m.use_even_offset = even
    m.offset = 0
    return m


def add_bevel_modifier(obj, width=0.02, segments=2, angle_deg=40):
    """Live, non-destructive version of bevel_all_sharp. Keep it live during
    blockout, apply before UV. Weight/angle-limited so only real edges round."""
    m = obj.modifiers.new('Bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle_deg)
    m.harden_normals = True
    return m


def apply_modifiers(obj):
    """Bake all modifiers into real geometry. Do this before UV/export.
    Order matters — modifiers apply top-to-bottom."""
    bpy.context.view_layer.objects.active = obj
    for m in list(obj.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError as e:
            print(f"Could not apply {m.name}: {e}")


# ---------------------------------------------------------------------------
# MEASUREMENT / VALIDATION HELPERS  (model to spec, not by vibes)
# ---------------------------------------------------------------------------

def dimensions(obj):
    """Return world-space (x, y, z) size in meters. Check against your target
    before moving on — a door should be ~2.0 m tall, a mug ~0.10 m."""
    return tuple(round(d, 4) for d in obj.dimensions)


def tri_count(obj):
    """Triangulated face count (what the engine actually pays for)."""
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def report(obj):
    """One-line health check to print after each stage."""
    ngons = sum(1 for p in obj.data.polygons if len(p.vertices) > 4)
    tris = sum(1 for p in obj.data.polygons if len(p.vertices) == 3)
    quads = sum(1 for p in obj.data.polygons if len(p.vertices) == 4)
    print(f"{obj.name}: dims={dimensions(obj)} m | tris(final)={tri_count(obj)} "
          f"| quads={quads} tris={tris} ngons={ngons} | scale={tuple(obj.scale)}")
