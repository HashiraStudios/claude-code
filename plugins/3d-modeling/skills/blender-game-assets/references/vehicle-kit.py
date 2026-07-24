"""
Vehicle kit — machine anatomy, executable.

Studied against pro blockbench/low-poly motorcycle references (Peter
Arkita's cafe racer among them). What separates an acceptable vehicle
from a tin toy is ANATOMY — every reference obeys this checklist:

  [ ] WHEELS ARE ASSEMBLIES: tire + recessed rim + hub disc + axle caps.
      A bare cylinder with a stub hub reads as a toy wheel. 12 segments
      (dodecagonal) is a legitimate stylized look — own it.
  [ ] VISIBLE TUBE FRAME connects everything: steering head → down tubes
      → engine-cradle rails → seat stays → tail. The vehicle must read
      as "a frame with masses attached"; nothing floats.
  [ ] THE ENGINE IS THE CENTERPIECE: a stack of cooling-fin plates plus
      a round crankcase drum, sitting INSIDE the cradle, is instantly
      "engine" at any resolution.
  [ ] FORK = two full-length tubes + two triple-clamp plates, headlight
      mounted BETWEEN the tubes. Rake: top behind bottom, tubes land ON
      the axle.
  [ ] BODYWORK IS LAYERED PANELS: tank + side panels + seat pad + tail
      cowl, overlapping — not one blob. Bevel every body mass.
  [ ] EXHAUST starts at the engine (header) and its tip ends PAST the
      wheel silhouette.
  [ ] TEXEL DENSITY SCALES WITH PART SIZE: a busy strip (cracked
      plaster, stone) at density ~1 turns small parts (rims, panels)
      into cracked turtle shell — drop density to ~0.5 on small parts
      so the texture softens into color variation.

Depends on the exec-all pattern (modeling-recipes, shape-language,
trim-sheet loaded into the same namespace) like every test script.
Each helper builds axis-aligned, maps, then rotates/places.
"""

import bpy
import math
from mathutils import Vector


def tube(name, p0, p1, mat, r=0.022, strip='planks', density=2.0, segs=8):
    """Frame/handlebar/exhaust-header tube between two world points.
    THE connector primitive: chain these and the machine stops floating."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    t = add_cylinder(name, radius=r, depth=d.length, segments=segs)
    assign_material(t, mat)
    trim_map_around(t, [i for i in all_polys(t)
                        if abs(t.data.polygons[i].normal.z) < 0.5],
                    strip, density=density)
    caps = [i for i in all_polys(t) if abs(t.data.polygons[i].normal.z) >= 0.5]
    if caps:
        trim_map(t, caps, strip, density=density)
    t.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    t.location = (p0 + p1) / 2
    return t


def wheel_asm(label, wx, r, w, mat, tread='stone', side='beam',
              rim_strip='plaster', hub_strip='planks'):
    """Full wheel assembly at x=wx standing on the ground plane:
    tire (tread wraps, dark sidewalls) + recessed rim (LOW density —
    see checklist) + hub disc + axle. Returns the part list."""
    made = []
    tire = add_cylinder(f"Tire{label}", radius=r, depth=w, segments=12)
    assign_material(tire, mat)
    trim_map_around(tire, [i for i in all_polys(tire)
                           if abs(tire.data.polygons[i].normal.z) < 0.5],
                    tread, density=1.0)
    trim_map(tire, [i for i in all_polys(tire)
                    if abs(tire.data.polygons[i].normal.z) >= 0.5],
             side, density=1.2)
    made.append(tire)
    for nm, rr, dd, strip, dens in (
            ("Rim", r * 0.72, w + 0.02, rim_strip, 0.5),
            ("HubD", r * 0.40, w + 0.05, hub_strip, 1.5),
            ("Axle", 0.055, w + 0.14, side, 2.0)):
        ob = add_cylinder(f"{nm}{label}", radius=rr, depth=dd, segments=12)
        assign_material(ob, mat)
        trim_map_around(ob, [i for i in all_polys(ob)
                             if abs(ob.data.polygons[i].normal.z) < 0.5],
                        strip, density=dens)
        capf = [i for i in all_polys(ob)
                if abs(ob.data.polygons[i].normal.z) >= 0.5]
        if capf:
            trim_map(ob, capf, strip, density=dens)
        made.append(ob)
    for ob in made:
        ob.rotation_euler = (math.radians(90), 0, 0)
        ob.location = (wx, 0, r)
    return made


def fin_stack(mat, center=(0, 0, 0.36), count=5, size=(0.36, 0.26, 0.026),
              gap=0.047, strip='planks', density=1.8):
    """Cooling-fin plates — the 'this is an engine' signal. Pair with a
    round crank drum (cylinder, axis Y) tucked under the lowest fin."""
    made = []
    for k in range(count):
        fin = add_box(f"Fin{k}", size, (0, 0, 0))
        assign_material(fin, mat)
        trim_map(fin, all_polys(fin), strip, density=density)
        fin.location = (center[0], center[1], center[2] + k * gap)
        made.append(fin)
    return made
