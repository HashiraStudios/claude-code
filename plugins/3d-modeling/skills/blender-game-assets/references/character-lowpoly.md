# Low-Poly Character Workflow (game-ready, palette-textured)

The hardest archetype: the mesh must LOOK good AND deform well. This guide is
the executable path for stylized characters (Synty / hyper-casual tier,
1–3k tris). For realistic characters you'd sculpt + retopo instead.

## Proportions (decide before modeling)

Measured in "heads" (head height as the unit):

| Style | Heads tall | Read |
|---|---|---|
| Chibi / hyper-casual | 2–3 | cute, mobile-friendly, big silhouette |
| Stylized adventurer (Synty-ish) | 4–5 | friendly but capable |
| Realistic | 7.5–8 | out of scope for this workflow |

Stylized rules: hands and feet ~1.5x realistic size (silhouette + readability),
neck short or absent, shoulders wide for heroes / narrow for cute. Pick total
height in meters first (e.g. 1.35 m villager) and derive part sizes.

## ORGANIC FORM RULE — primitive assembly is below the bar

(Lesson from the dragon: a character assembled from unmodified
spheres/cones passed the layout check against its model sheet and still
read as a toy mannequin — the same failure as the first "tin can"
motorcycle, on a creature.)

- **Raw primitives are scaffolding, never the deliverable.** Every major
  mass must be SHAPED after placement: cheek/brow/haunch volumes,
  taper/bulge on limbs, a carved mouth line. A sphere with eye stickers
  is not a head.
- **Creature faces have mandatory features**: brow ridge, muzzle with a
  mouth line (geometry or texture), nostrils at hero tier, cheek volume.
  A face without a mouth FAILS the gate regardless of silhouette.
- **The critique gate must compare FORM, not layout**: render the
  blockout from the sheet's exact views and compare SILHOUETTES
  feature-by-feature against the concept (checklist the concept's shapes:
  which masses exist in the drawing but not in the mesh?). Matching
  positions/proportions while missing sculpted forms is a FAIL.
- **For organic characters, prefer a generated base**: best supplier is
  **Hunyuan3D-2mv** fed 4 gpt-image-2 views (front/left/back/right,
  generated from the approved concept, octree_resolution=512) →
  decimate ~12k tris — fully symmetric, concept-faithful sculpt with
  eye sockets, brow, mouth, claws in-mesh. Single-image Hunyuan3D-2 is
  the quick variant; Cube3D (text prompt, permissive license) the
  license-safe fallback; MeshAnything V2 tested and rejected (fragments
  complex creatures). License: Hunyuan 2.0 non-commercial — use 2.1 for
  commercial. The skill adds EYE DECALS placed by READING the front
  reference view (threshold the dark eye clusters, map image→mesh via
  the two bounding boxes, raycast to the surface — geometry probes latch
  onto the muzzle), thin-feature region masks, painted-bake, spatial-
  group rig. Procedural construction remains the path for hard-surface
  and part-based humanoids (below), where boxes/cylinders + joint rings
  are the idiom.

## Construction: part-based, joined, with joint rings

Industry-standard for this tier — parts are separate shells joined into ONE
mesh (no welding needed; shells hide inside neighbors):

- **Torso**: extrusion chain pelvis → waist → chest → shoulder cap
  (`extrude_faces` + scale the cap verts). The waist ring IS a deformation loop.
- **Head**: beveled box (or 8-side cylinder), sitting on a short neck cylinder.
- **Limbs**: 8-sided cylinders. **Add one ring at each elbow/knee** — subdivide
  only the lengthwise edges: `edges = [e for e in bm.edges if lengthwise]`,
  `bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1)`. Without that ring the
  joint collapses when bent; with it, the bend reads clean even rigid-skinned.
- **Hands**: mitt boxes (no fingers below hero tier). **Feet**: boxes shifted
  forward, beveled.
- **FACE IDENTITY — the front must WIN** (ground truth from the KayKit
  Adventurers CC0 kit, github.com/KayKit-Game-Assets): the face needs BIG
  dark oval eyes (~1/5 of head width EACH, tall ellipses, wide apart, at
  the vertical middle of the face), a protruding NOSE wedge, and a brow
  line (helmet edge / goggle strap / hair fringe). Tiny eyes lose to any
  strong back feature (hair patch, hood, scarf) and the character reads
  as facing BACKWARDS ("face on the nape"). KayKit numbers: ~2.5 heads
  tall, head BIGGER than the torso (head 1.09 vs body 0.92 on the
  Knight), no neck, stubby limbs, big hands/boots.
- Join everything (`object.join`) AFTER painting each part (UVs survive joins;
  z-predicates are in each part's LOCAL space before the join).

Validate the face with a straight-on textured front view
(`render_turntable(body, shading='TEXTURE')`) — the 3/4 beauty angles can hide
a broken or missing face.

**Atlas split**: keep the character on its OWN palette atlas, separate from the
environment atlas (skin/hair/clothes cells vs grass/wood/stone cells). Two
materials for a whole populated scene is the industry-standard split.

## Painting (palette-texturing.py)

Paint per part BEFORE the join. Typical mapping: skin flat cell; shirt on torso
+ upper arms (sleeve = polys above the elbow ring); pants on pelvis + legs;
boots/hair dark cells; ONE accent (scarf, cap, belt). Hair = head-box top faces
plus back faces (`p.center.z > top_band or p.normal.y > 0.5`).

## Rig + pose test (the "game-ready" proof)

A character isn't validated until it bends. Minimal rig, all in Python:

```python
bpy.ops.object.armature_add(enter_editmode=True)
arm = bpy.context.active_object
ebs = arm.data.edit_bones
spine = ebs[0]; spine.name = 'spine'
spine.head = (0, 0, 0.76); spine.tail = (0, 0, 1.10)
def bone(name, head, tail, parent):
    b = ebs.new(name); b.head = head; b.tail = tail
    b.parent = ebs[parent]; return b
bone('head',      (0, 0, 1.10), (0, 0, 1.40), 'spine')
bone('arm.L',     (0.21, 0, 1.08), (0.21, 0, 0.88), 'spine')
bone('forearm.L', (0.21, 0, 0.88), (0.21, 0, 0.58), 'arm.L')
# ... mirror for .R, thigh/shin per leg ...
bpy.ops.object.mode_set(mode='OBJECT')
```

Skinning — **explicit per-part bone groups, declared BEFORE the join**:
right after building each part, create a vertex group named for its bone
and assign all its verts (split limbs at the joint ring by local z). Vertex
groups merge by name on join; then `parent_set(type='ARMATURE_NAME')`.
Deterministic, no tearing, the standard hyper-casual look.

Do NOT trust `ARMATURE_AUTO`: bone heat can "succeed" while assigning
NOTHING (silent total failure on overlapping chibi shells — verified: op
reported OK with 456/456 vertices empty). And per-vertex nearest-bone on
the JOINED mesh tears shells apart (shoulder verts ride the arm bone).
ALWAYS verify programmatically after any skinning path:

```python
empty = [v for v in body.data.vertices
         if not v.groups or all(g.weight < 1e-4 for g in v.groups)]
print(f"weight check: {len(empty)}/{len(body.data.vertices)} empty")
# fallback for stragglers: rigid nearest-bone per vertex
```

**ALWAYS run a weight-repair pass after auto weights**: bone heat is
unreliable on tiny disconnected accessory shells — an eye or goggle lens
partially weighted to an arm bone stays put in T-pose and RIDES AWAY with
the first pose (the bug only shows posed, which is why it slips through
T-pose review). Force accessory shells to their anatomical bone:

```python
hg = body.vertex_groups.get('head')
for v in body.data.vertices:
    if v.co.z > neck_top_z:          # everything above the neck = head
        for g in list(v.groups):
            body.vertex_groups[body.vertex_groups[g.group].name].remove([v.index])
        hg.add([v.index], 1.0, 'REPLACE')
```

And pose-test EVERY accessory: the bend test isn't just for joints — it is
what exposes bad accessory weights.

Pose test: rotate `arm.L/R` and `thigh.L/R` ±20–30°, bend a knee/elbow ring,
then `render_turntable` + `render_beauty`. PASS = joints bend without the
mesh collapsing or shells popping visibly. Reset pose before FBX export
(`bake_anim=False`, armature included; engine retargets from there).

## CONCEPT-FIRST accessory pipeline (the professional order of operations)

Modeling an accessory straight from imagination produces "esquisito" —
design it FIRST, model against the design. Validated end-to-end flow:

1. **Render the base** (clean textured front ortho, white background).
2. **Concept ON the character**: image-EDIT endpoint (`gpt-image-1`,
   `/v1/images/edits`, image = the render): "dress this character with
   <accessory>, keep character/style/camera unchanged". The generator
   designs proportions, materials and details in context.
3. **Isolate as a model sheet**: second edit call on the concept:
   "ONLY the accessory, no character, two orthographic views side by
   side (front | side), flat white background". This is the blueprint.
4. **Model against the views**: read shape facts off the sheet (dome
   wraps the skull and opens a face arch; flaps taper and flare; rims
   are ~25% of lens radius...) and build with the normal recipes.
   Compare renders to the sheet each critique pass.
5. Fit to measurements, `assert_attached`, bone-parent, pose test.

Probe design note: an attachment probe must sit ON the accessory's
contact surface, not at the anchor's center (a center probe measures
"how deep inside", which fails at any tolerance and means nothing).

**A covering shell must be solved against the covered surface's MEASURED
profile**: bin the anchor mesh's top surface by horizontal radius
(`max z per ρ ring`) and choose the shell's radius/center/squash so the
inner surface clears every ring. A sphere sized to hug the SIDES of a
flat-topped head intersects its crown — the anchor pokes through and
reads as a texture error (pink patch on the cap). Verify with a
clearance probe at the crown, then conform surface details (seam
ridges) to the shell equation, never as floating straight boxes.

**Parts must CHAIN, not stack** (the "empilhado" failure): every piece
declares what it connects to, and the geometry expresses it — the flap's
top edge tucks UNDER the dome rim (overlap, not adjacency), the strap is
a torus whose tube intersects the dome surface (a constant-radius band
around a curved dome floats), goggle rims interpenetrate the strap.
And FIT TO MEASURED ANATOMY: probe the feature you must cover first
(ear verts: |x|max region → its y/z box) and assert coverage in code —
`flap z-range ⊇ ear z-range` — the eyeballed flap missed the ears by
half their height.

## Accessorizing an existing rigged base (the KayKit workflow)

Building gear for a professional CC0 base (KayKit & co.) is faster than
building the whole character, and it's how studios ship skins. Validated
recipe:

1. **Measure the target, never eyeball**: import the GLB, print the bbox
   of the anchor mesh (head, hand) and the bone heads/tails — all sizes
   derive from those numbers. And probe AT THE MOUNT HEIGHT: a global
   extreme (deepest back point) lies about the local surface — the back
   curves, so a plate placed at global ymax floats at plate height.
2. Build accessories with our normal recipes + own palette material,
   FITTED to the measurements (dome cap = hemisphere shell + solidify;
   goggles BELOW the cap edge or the dome swallows them).
3. `assert_attached()` every piece against its anchor mesh.
4. Join per anchor (head kit / chest kit) and parent to the BONE:
   ```python
   obj.parent, obj.parent_type, obj.parent_bone = arm, 'BONE', 'head'
   frame = arm.matrix_world @ b.matrix_local @ Matrix.Translation((0, b.length, 0))
   obj.matrix_parent_inverse = frame.inverted()   # bone frame is at the TAIL
   ```
   (KayKit even ships slot bones — `handslot.l/r` — for weapons.)
5. **Pose test is the proof**: rotate the anchor bone and render — the
   kit must follow. A kit that only looks right in rest pose is untested.

## Character critique additions

On top of the standard checklist:
- [ ] Silhouette readable at 64px tall (thumbnail test — shrink the render).
- [ ] Proportions match the chosen heads count.
- [ ] Joint rings present at elbows/knees; bend test passes.
- [ ] Hands/feet oversized enough to read.
- [ ] Palette: ≤6 cells on the body, one accent, skin warm against clothes.
- [ ] Tri budget: 1–3k stylized (this workflow lands ~1–1.5k).
