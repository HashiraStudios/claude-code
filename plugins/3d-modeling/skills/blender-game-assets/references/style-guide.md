# Low-Poly Style Guide — harmonious color, beautiful mesh, fast render

The goal is three-way: **aesthetic harmony** (color/form), **clean topology**
(the mesh itself is presentable), and **performance** (few tris, one draw call).
These reinforce each other — the palette-atlas workflow exists precisely
because it delivers all three at once.

## Color: build ONE palette per scene, then obey it

- **8–16 colors total.** Constraint is the style. Every prop samples the same
  atlas (`palette-texturing.py`); nothing gets its own texture.
- **Value hierarchy first, hue second.** Squint test: the scene must read in
  grayscale. Ground darkest-mid, hero props highest contrast, filler props low
  contrast. If everything is equally saturated, nothing reads.
- **One dominant hue family + one accent.** E.g. greens/browns + one warm red
  accent used sparingly (a mushroom, a flag, a lantern). The accent is what
  makes the scene feel designed instead of generated.
- **Shift hue, not just value, in shadows.** A "darker green" cell should lean
  toward blue-green, not just black-green — this is the difference between
  muddy and rich. Encode it in the gradient strips.
- **The gradient trick**: vertical gradient strips fake ambient occlusion and
  sky light (light top → dark bottom) for free. Use on foliage, rocks, walls,
  cliffs. Flat cells for small parts and man-made surfaces.

## Mesh beauty: what makes topology "bonita"

A mesh is presentable when someone opening the wireframe nods:

1. **Silhouette carries the design.** Detail that doesn't change the outline or
   catch a highlight is wasted budget. Test: matcap render, front + 3/4 views.
2. **Even, intentional density.** Faces of similar size across a surface; density
   spent where curvature/deformation lives, not sprinkled evenly.
3. **Flat shading is a feature.** Low-poly reads through its facets — do NOT
   auto-smooth foliage/rocks; do bevel+smooth man-made hero edges.
4. **No junk:** no n-gons in curved regions, no long thin slivers, no doubled
   verts, no interior faces, scale applied. `report()` + `cleanup()` after
   every session.
5. **Deliberate segment counts:** cylinders 8–16 sides for props (8 reads
   "chunky stylized", 16 reads "smooth"); icospheres subdiv 1 for blobs.
   Consistency across a set matters more than the number.

## Performance: the numbers that matter

- **Draw calls beat polycounts** on modern hardware. One 64px atlas + one
  material for the whole set is a bigger win than shaving 20% of tris.
- Budgets (tris): filler prop 100–500 · standard prop 300–1000 · hero prop
  1–3k · character 3–10k. A palette-textured scene of 15 props ≈ one PBR chair.
- The 64px atlas needs **no mipmap chain worth mentioning, no normal map, no
  roughness map** — memory cost is effectively zero.
- Collapse-UV flat cells mean **no visible seams and no filtering artifacts**
  (sample sits at the cell center, nearest-neighbor interpolation).
- Trim sheets are the same idea for architecture (tiling strips instead of
  cells) — use them when walls/floors need real surface detail.

## Composition checklist for a prop set / diorama

- [ ] All props share the single palette atlas (1 material).
- [ ] Scene reads in grayscale (value hierarchy).
- [ ] One accent color, used in ≤ 2 places.
- [ ] Gradients on organic masses, flats on small/man-made parts.
- [ ] Consistent segment counts and bevel widths across the set.
- [ ] Ground/base slightly darker than hero props.
- [ ] render_beauty() from two angles; critique like the form pass, but for
      color: any prop shouting? any prop invisible? any value merge?
