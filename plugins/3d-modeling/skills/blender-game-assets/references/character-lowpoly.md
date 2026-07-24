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

## Character critique additions

On top of the standard checklist:
- [ ] Silhouette readable at 64px tall (thumbnail test — shrink the render).
- [ ] Proportions match the chosen heads count.
- [ ] Joint rings present at elbows/knees; bend test passes.
- [ ] Hands/feet oversized enough to read.
- [ ] Palette: ≤6 cells on the body, one accent, skin warm against clothes.
- [ ] Tri budget: 1–3k stylized (this workflow lands ~1–1.5k).
