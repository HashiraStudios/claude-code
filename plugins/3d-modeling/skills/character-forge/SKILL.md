---
name: character-forge
description: Production pipeline for game-ready stylized 3D characters from a text idea or a reference image. Generates concept + orthographic views (gpt-image-2), 3D shape (Hunyuan3D-2mv on RunPod), retopology (organic/hard-surface fork), PBR textures (Hunyuan3D-2.1 Paint), chain rig with deformation gates, animation clips and MP4 previews. Use when the user wants a complete character/creature/mecha model for a game, from scratch or from a reference image. Single-mesh characters only (multi-part assembly is experimental).
---

# Character Forge — idea → game-ready character in ~25 min / ~US$0.15

Proven end-to-end on: chibi dragon (organic), frog mecha (hard-surface
hybrid). **APPROVED scope: single-mesh characters.** Multi-part
characters needing assembly (e.g. a kid inside a costume hood) are NOT
production-approved — the union results are below bar; treat as
experimental only.

## Requirements (workstation)

- Blender 4.x on PATH (headless use: `LIBGL_ALWAYS_SOFTWARE=1 blender --background`)
- `OPENAI_API_KEY` env var (gpt-image-2 access)
- `RUNPOD_API_KEY` env var (on-demand GPU, SECURE cloud; each character
  costs ~US$0.10-0.15 across 2 pods, auto-terminated)
- License note: Hunyuan3D-2mv (shape) is **non-commercial** (2.0
  family); Hunyuan3D-2.1 (paint/PBR) has the community license. For a
  fully commercial pipeline, swap the shape stage to 2.1 single-image
  or validate 2.1-mv availability. Flag this to the user per project.

## The pipeline (run steps in order; every step has a QA gate)

```
1. VIEWS      python scripts/gen_views.py --prompt "..." [--reference img.png] --out work/char
              → concept.png + views/{front,left,back,right}.png
              GATE: inspect views — consistent colors/features/expression?
              Back view must NOT invent front features (no teeth on the
              back of a hood). Regenerate a single view if off.

2. SHAPE      python scripts/runpod_run.py shape --views work/char/views --out work/char/shape.glb
              → dense mesh ~1-2M tris (octree 512 = site's 1.5M mode)
              GATE: clay render — symmetric? all features present?

3. RETOPO     blender --background --python scripts/retopo.py -- work/char/shape.glb work/char/retopo.obj organic 14000
              organic → QuadriFlow pure quads (deformation)
              hard    → edge-preserving decimate ~30k (panel lines; mecha
                        visors/shallow features MUSH under quadriflow)
              GATE: clay render — features held? quads>0 when organic
              (quadriflow silently no-ops on non-manifold input; the
              script cleans + verifies, but CHECK the count).

4. PAINT PBR  python scripts/runpod_run.py paint --mesh work/char/retopo.obj --ref work/char/concept.png --out work/char/painted.glb
              → GLB with 2K basecolor + 2K metallic-roughness (glTF)
              NOTE: pod status may report FAIL rc=-11 AFTER writing the
              GLB (benign bpy exit segfault) — validate by artifact
              size, not exit status.

5. RIG        blender --background --python scripts/autorig.py -- work/char/painted.glb work/char
              → chained skeleton on MEASURED pivots + heat skinning +
              soft anatomical masks + 6 deformation-test renders.
              GATE: open deform_*.png. No tears, no stretched membranes,
              no collapsed joints. The printed stats must show most
              vertices blended across 2+ bones and very few at 1.0.

6. ANIMATE    blender --background --python scripts/animate_pro.py -- work/char/painted.glb work/char/anim
              → anim/{idle,walk,hop,turntable}.mp4 + anim/animated.glb
              (all actions embedded; Three.js/Unity/Unreal/Godot ready).

7. PREVIEW    blender --background --python scripts/preview_video.py -- work/char/anim/animated.glb work/char/preview.mp4
              → 360° MP4. ALWAYS deliver MP4, never GIF.
```

## Rigging rules (learned the hard way — a 2/10 rig taught these)

- **WELD FIRST.** A GLB duplicates vertices at every UV/normal seam.
  The twins get different weights and TEAR APART when posed (this asset
  imported as 425 disconnected islands / 11k non-manifold edges).
  `remove_doubles(dist=1e-4)` before binding fixed the head ripping off
  the body — and it also let bone-heat succeed with ZERO orphan verts.
  Blender stores UVs per loop, so welding never harms the texture.
- **One bone per limb is not a rig.** Chains are mandatory:
  Clav → UpperArm → Forearm → Hand, Thigh → Shin → Foot, and a spine
  Hips → Spine → Chest → Head. Without an elbow/knee the limb can only
  swing rigidly — the #1 source of "stiff".
- **Measure the pivots, never guess them.** Sample cross-sections along
  each limb axis: joints are the local minima of the radius profile
  (hard-surface joints literally narrow there). See the analysis block
  in autorig.py.
- **Skin with bone-heat, then LOCALIZE.** Heat gives smooth falloff but
  bleeds — an arm bone grabbing chest verts produces stretched membranes
  at the shoulder. Attenuate every weight by an anatomical region mask,
  but with a SOFT band (smoothstep over ~0.07): a binary mask re-creates
  hard weight edges and the mesh tears at the region boundary.
- **Smoothing re-bleeds** — mask, smooth, then mask again.
- **Verify numerically**: count verts with max weight > 0.995 (should be
  a small minority, body cores only) and verts with 2+ influences
  (should be the large majority). On this asset: 87% blended.
- **Verify visually**: single-joint extreme poses per joint. A tear
  hides in a video and screams in a still.

## Animation rules (the fix for "stiff, nota 2")

- **Overlapping action is the whole game.** Every bone lags its parent:
  spine +1f, chest +2f, head +3f, forearms +5f, hands/antenna +6f.
  Nothing moves as one rigid block.
- **Seamless loops need wrapped tangents**, not just matching end poses.
  Emit each key one period BEFORE and AFTER the range, then render only
  the range — the interpolator then has real neighbours on both sides
  and the loop has no hitch. (Lag is a phase shift, so it stays cyclic.)
- **Use the curves.** Per-keyframe interpolation + easing, not one flat
  auto-bezier: SINE/EASE_OUT to settle, QUAD/EASE_IN to drive into a
  contact, BACK/EASE_OUT to overshoot on impact, QUAD/EASE_IN_OUT to
  hang at an apex.
- **Breakdowns off the midpoint** so arcs favour one extreme, and
  **moving holds** so an idle never freezes.
- **Real walk mechanics**: contact / down / passing / up, knees bending
  on the swing, feet rolling, hips twisting, arms counter-swinging with
  the forearms trailing.
- Blender encodes MP4 itself (`file_format='FFMPEG'`, MPEG4/H264) — no
  system ffmpeg needed on the workstation. Never ship GIF.

## Hard-won rules (do not relearn these)

- **gpt-image-2 for all image generation** (v1 views are not consistent
  enough). Spell out per-view consistency in each prompt (same colors,
  same expression, feature checklist) and describe the BACK explicitly.
- **RunPod**: SECURE cloud, RTX 4090, official pytorch 2.4 cu124 image
  (devel for paint — it compiles CUDA). First boot step asserts CUDA
  (broken machines exist); if a pod sits >10 min with no container,
  terminate and re-roll. Inputs go INTO the pod via its own HTTP PUT
  endpoint (public file hosts all block datacenter traffic). All pins
  and the full playbook: `../blender-game-assets/references/landscape-research.md`.
- **OBJ round-trips in Blender**: import with
  `forward_axis='NEGATIVE_Z', up_axis='Y'` + apply rotation, or every
  z-predicate silently misses (mesh lands Y-up).
- **Region masks / feature placement** (if hand-texturing instead of
  Paint): thin-feature raycast detector + reference-image-driven eye
  placement — see `../blender-game-assets/references/`.
- **Experimental (NOT approved)**: decomposition/part-swap assembly
  (container-empty + inserted part). Documented in
  character-lowpoly.md for future work; do not offer as production.
