---
name: character-forge
description: Production pipeline for game-ready stylized 3D characters from a text idea or a reference image. Generates concept + orthographic views (gpt-image-2), 3D shape (Hunyuan3D-2mv on RunPod), retopology (organic/hard-surface fork), PBR textures (Hunyuan3D-2.1 Paint), spatial-group rig, pose test and 360 GIF preview. Use when the user wants a complete character/creature/mecha model for a game, from scratch or from a reference image. Single-mesh characters only (multi-part assembly is experimental).
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
- Python 3 with `pillow` (GIF assembly): `pip install pillow`
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

5. RIG        blender --background --python scripts/rig_character.py -- work/char/painted.glb work/char/final.glb biped_chibi
              configs: biped_chibi (dragon-like: head/arms/legs/tail),
              biped_mecha (rigid parts, no tail), quadruped (stub).
              GATE: pose render — no tears. Thin fins tolerate ~20° of
              summed lateral bend; keep test poses inside that.

6. ANIMATE    blender --background --python scripts/animate_character.py -- work/char/painted.glb work/char/anim biped_mecha
              → anim/{idle,walk,hop,turntable}.mp4 + anim/animated.glb
              (all actions embedded; imports into Three.js/Unity/Unreal/
              Godot). Rigs: biped_mecha, biped_chibi. This step also
              rigs, so it replaces step 5 when you want clips.

7. PREVIEW    blender --background --python scripts/preview_video.py -- work/char/final.glb work/char/preview.mp4
              → 48-frame 360° MP4. ALWAYS deliver MP4, never GIF
              (GIF failed to play for the user; MP4 is universal).
```

## Animation notes (stage 4)

- Rig has a **Root** bone anchored at the feet, unweighted, parenting
  Body and the legs: Root translation = hop/bob, Root z-scale =
  squash & stretch about the ground, and legs hang off Root so body
  rotation does not drag them.
- Clip library: `idle` (48f loop, breathing + weight shift), `walk`
  (32f loop, contralateral limbs + body bob/roll), `hop` (44f, frog
  arc: anticipation → launch → apex → impact → rebound), `turntable`
  (48f spin).
- Review before delivering: render the key frames as PNG stills and
  inspect the extremes (crouch, launch, apex, contact) — video can hide
  a tear that a still makes obvious.
- Blender encodes MP4 itself (`file_format='FFMPEG'`, MPEG4/H264) — no
  system ffmpeg required, which also means no extra install on the
  workstation.

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
