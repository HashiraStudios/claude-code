# Goal → Technique Map

> Adapted from the organizing idea of blender-reference.takayustudio.jp:
> **"from the result you want to make, to the technique you look at next."**
> Don't start from a menu. Start from *what the thing is*, pick the track, run
> the recipe. All recipe names below are functions in `modeling-recipes.py`.

## How to use this map
1. Name the object in plain words ("a wooden crate", "a ceramic mug", "a chain-link fence").
2. Match it to a **form archetype** below.
3. Follow that row's recipe chain, then run the **critique loop** (see `topology-and-critique.md`).

---

## Real-scale first (do this before any modeling)

Model to real measurements so props sit right next to each other and export clean.

```python
import bpy
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'METERS'
scene.unit_settings.scale_length = 1.0   # 1 BU = 1 m
```

Reference sizes (meters): door 0.9 x 2.03 · chair seat 0.45 high · table 0.75 high ·
mug 0.10 tall · car ~4.5 long · human 1.7–1.8 tall · brick 0.19 long.
Use `dimensions(obj)` after blockout and correct before detailing.

---

## Form archetypes

| You want to make… | Archetype | Recipe chain | Notes |
|---|---|---|---|
| Crate, cabinet, book, brick, building block | **Boxy hard-surface** | `add_box` → `inset_faces` (panels) → `bevel_all_sharp` | Keep scale 1.0 by sizing the box, not scaling a cube. |
| Mug, bottle, cup, vase, column, wheel, plate | **Radial / lathe** | draw profile verts → `spin_lathe` → `bevel_edges` on rims | `steps=24` reads round; `steps=8` reads faceted-on-purpose. |
| Pipe, cable, handle, rail, tube joint | **Extruded profile / bridge** | `add_cylinder` or profile → `extrude_faces` along a path, or `bridge` two loops | Mirror if symmetric. |
| Sword, gun, tool, machine part | **Layered hard-surface** | `add_box` blockout → `loop_cut` for control → `inset`/`extrude` greebles → `add_bevel_modifier` | Model half + `add_mirror`. |
| Fence, stairs, railing, window grid, chain | **Modular / array** | build one unit → `add_array` (× rows/cols) → `apply_modifiers` | Combine two arrays for grids. |
| Wall section, floor, modular kit piece | **Trim / tileable** | `add_box` to grid size → align UVs to a trim sheet | Snap dims to a power-of-two grid (0.5/1/2 m). |
| Rock, log, terrain chunk, debris | **Organic hard edges** | `add_box` → `subdivide_smooth` → sculpt/randomize → `bevel` | Triangles OK; no deformation here. |
| Character, creature, hand, face | **Organic deforming** | blockout primitives → `add_mirror` → `loop_cut` at joints → retopo quads | See hard-surface-vs-organic below; edge loops follow muscle flow. |
| Fender, arch, vault, half-pipe, awning | **Arc shell** | `add_cylinder(cap=False)` → delete all faces below an arc cutoff → `add_solidify` → `trim_map_around` | Filter by the coord that becomes "up" AFTER the placement rotation (e.g. local **Y** for a wheel-style 90° X-rotation) — never by the axial coord: every side face sits at axial center 0 and the whole shell deletes. Map before rotating. |
| Foliage, leaf, blade, cloth card | **Card / plane** | plane → `add_solidify` (thin) → alpha texture | Keep 2-sided or disable backface cull in engine. |
| Scattered grass/rocks/props over a surface | **Procedural** | Geometry Nodes scatter (see SKILL.md) | Bake to mesh before export. |

---

## Hard-surface vs Organic — the fork that matters most

These are **different topology philosophies**. Pick consciously.

### Hard-surface (props, machines, architecture)
- Silhouette comes from **bevels catching light**, not from density. Use
  `bevel_all_sharp` / `add_bevel_modifier`.
- Triangles and n-gons are **acceptable on flat, non-deforming faces**.
- Support loops near a bevel keep it crisp under any shading.
- Model half and `add_mirror` whenever symmetric.
- Budget goes into the *readable edges*, not smoothness.

### Organic (anything that bends/animates)
- **Quads only** in deforming areas — triangles pinch, n-gons shade wrong.
- **Edge loops follow deformation**: rings around joints (elbow, knee, knuckle),
  loops around eyes/mouth. This is what lets a rig bend cleanly.
- **Poles** (3- or 5-edge vertices) are fine but keep them *off* the crease
  lines and away from high-deformation zones.
- Even quad density = even texel density = predictable skinning.
- Symmetry via `add_mirror` until the very end.

If you can't tell which fork you're on, ask: *does this surface ever bend?*
Yes → organic rules. No → hard-surface rules.

---

## The block-out method (applies to every archetype)

Never model the final detail first. Work coarse → fine:

1. **Massing** — biggest volumes only, real dimensions (`add_box`/`add_cylinder`).
   Check proportions with `dimensions()` and the critique loop.
2. **Major forms** — cut the silhouette, split volumes, `loop_cut` control edges.
3. **Secondary forms** — panels (`inset`), protrusions (`extrude`), openings.
4. **Detail** — bevels, greebles, small parts. Last, and only where the camera sees.

Approve the silhouette at step 1–2 *before* spending polygons on step 4.
This is the single biggest gap between "LLM generated a mesh" and "a human built it."
