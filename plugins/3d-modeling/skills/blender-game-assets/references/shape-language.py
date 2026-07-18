"""
Shape-language deformers — the Supercell/Riot style tier, executable.

WHY STRAIGHT PRISMS LOOK AMATEUR
--------------------------------
Supercell (Clash/Brawl) and Riot style reads come from FORM, not texture:
  * NOTHING IS STRAIGHT. Walls bulge, trunks taper, chimneys lean, barrels
    swell. A straight cylinder reads "programmer art"; the same cylinder
    with a 25% belly bulge reads "toy".
  * EXAGGERATE THE SIGNATURE. Pick the one element that defines the object
    and push it 150-200%: Clash houses are half ROOF; a hero axe is mostly
    BLADE. Shrink whatever competes with it.
  * BIG / MEDIUM / SMALL. One dominant mass (~70%), one supporting mass
    (~20%), small accents (~10%). Same-size shapes = no rhythm. (Riot:
    "detail everywhere is as good as no detail" — leave areas of rest.)
  * TILT FOR CHARM. Perfect verticals are dead; 3-8 degrees of lean makes
    a prop feel hand-made and alive. Tilt the chimney, cock the hat.
  * SOFT TOY EDGES. Generous bevels (2-3 segments) everywhere — light wraps
    around corners instead of snapping.

THE DEFORMERS
-------------
All operate on mesh vertices in LOCAL space, along a chosen axis, using a
normalized 0..1 parameter t over the mesh's extent on that axis.
IMPORTANT: a 6-face box cannot bend or bulge — subdivide first
(loop_cut / subdivide_rings below), deform, THEN unwrap and paint.

  taper(obj, start, end)        cone-ify: scale cross-section from bottom
                                to top (trunks, towers, boots)
  bulge(obj, amount, center)    gaussian belly (barrels, bushes, muscles)
  lean(obj, amount, dir)        shear: top slides sideways, base planted
                                (chimneys, fence posts, plants)
  curve(obj, amount, dir)       quadratic arc (branches, horns, banners)
  squash(obj, factor)           volume-preserving squash/stretch anchored
                                at the base (make it chunkier: factor<1)
"""

import bpy
import math
import bmesh


def _axis_t(obj, axis):
    ai = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    cs = [v.co[ai] for v in obj.data.vertices]
    lo, hi = min(cs), max(cs)
    span = (hi - lo) or 1.0
    return ai, lo, span


def _perp(ai):
    return [(i) for i in range(3) if i != ai]


def _center(obj, idxs):
    vs = obj.data.vertices
    return [sum(v.co[i] for v in vs) / len(vs) for i in range(3)]


def subdivide_rings(obj, cuts=3, axis='Z', min_len=0.02):
    """Add rings across edges that run along `axis` so deformers have
    geometry to shape. Works on boxes and cylinders alike."""
    ai = {'X': 0, 'Y': 1, 'Z': 2}[axis]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = [e for e in bm.edges
             if abs(e.verts[0].co[ai] - e.verts[1].co[ai]) > min_len]
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=cuts, use_grid_fill=True)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def taper(obj, start=1.0, end=0.7, axis='Z', power=1.0):
    """Scale the cross-section from `start` (t=0, bottom) to `end` (t=1)."""
    ai, lo, span = _axis_t(obj, axis)
    pa, pb = _perp(ai)
    c = _center(obj, None)
    for v in obj.data.vertices:
        t = ((v.co[ai] - lo) / span) ** power
        f = start + (end - start) * t
        v.co[pa] = c[pa] + (v.co[pa] - c[pa]) * f
        v.co[pb] = c[pb] + (v.co[pb] - c[pb]) * f
    obj.data.update()


def bulge(obj, amount=0.25, center=0.5, width=0.4, axis='Z'):
    """Gaussian belly: +amount at `center`, fading over `width`."""
    ai, lo, span = _axis_t(obj, axis)
    pa, pb = _perp(ai)
    c = _center(obj, None)
    for v in obj.data.vertices:
        t = (v.co[ai] - lo) / span
        f = 1.0 + amount * math.exp(-((t - center) / width) ** 2)
        v.co[pa] = c[pa] + (v.co[pa] - c[pa]) * f
        v.co[pb] = c[pb] + (v.co[pb] - c[pb]) * f
    obj.data.update()


def lean(obj, amount=0.12, dir='X', axis='Z'):
    """Shear: the top slides `amount * height` sideways, base stays planted."""
    ai, lo, span = _axis_t(obj, axis)
    di = {'X': 0, 'Y': 1, 'Z': 2}[dir]
    for v in obj.data.vertices:
        t = (v.co[ai] - lo) / span
        v.co[di] += amount * span * t
    obj.data.update()


def curve(obj, amount=0.15, dir='Y', axis='Z'):
    """Quadratic arc: offset grows with t^2 (branches, horns, banners)."""
    ai, lo, span = _axis_t(obj, axis)
    di = {'X': 0, 'Y': 1, 'Z': 2}[dir]
    for v in obj.data.vertices:
        t = (v.co[ai] - lo) / span
        v.co[di] += amount * span * t * t
    obj.data.update()


def squash(obj, factor=0.85, axis='Z'):
    """Volume-preserving squash (factor<1) / stretch (>1), anchored at the
    base so the object stays planted. Chunkier = more toy-like."""
    ai, lo, span = _axis_t(obj, axis)
    pa, pb = _perp(ai)
    c = _center(obj, None)
    s = 1.0 / math.sqrt(factor)
    for v in obj.data.vertices:
        v.co[ai] = lo + (v.co[ai] - lo) * factor
        v.co[pa] = c[pa] + (v.co[pa] - c[pa]) * s
        v.co[pb] = c[pb] + (v.co[pb] - c[pb]) * s
    obj.data.update()
