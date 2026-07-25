# AI 3D Generation Landscape (researched 2026-07)

Where this skill sits among everything that exists, and what to borrow.
The core tension: image-to-3D reconstruction is FAITHFUL but produces
marching-cubes sludge; beautiful topology comes from four other camps.

## Camp A — Native mesh generation (autoregressive "artist mesh" models)
Generate the mesh face-by-face like an artist would, learning topology
itself. The lineage: PolyGen → MeshGPT (VQ-VAE + GPT decoder) →
**MeshAnything V1/V2** (ICLR 2025; shape-CONDITIONED — takes any dense
3D and regenerates it with artist topology, hundreds× fewer faces =
"retopo as generation") → **Meshtron** (NVIDIA, 64k faces, hourglass AR)
→ DeepMesh / Mesh-RFT (RL fine-tuning for topology quality) →
**Hunyuan3D-PolyGen** (Tencent, production "art-grade", tri+quad) →
QuadGPT / QuadLink (native quad AR). **Roblox Cube 3D**: open-source
1.8B model trained on native GAME assets (not photos) — stylized,
engine-ready by construction; text→mesh via 3D tokens.
USE: as a blockout supplier for organic shapes we can't easily code, or
as retopo for any dense mesh (MeshAnything's conditioning is the key
trick — dense in, artist mesh out).

## Camp B — Program synthesis / code (THIS SKILL's camp)
LLMs write procedural code; topology is clean BY CONSTRUCTION.
**LL3M** (threedle, 2025): multi-agent LLMs writing Blender Python with
a BlenderRAG (1.7k docs) + visual self-critique + user co-creation loop
— the academic twin of this skill (we add: executable verification
probes, measured fitting, staged human gates — which LL3M lacks).
Also: BlenderMCP, 3DCodeBench (benchmark for agentic procedural
modeling), DI-PCG (inverse procedural), **Sloyd** (commercial parametric
generators — clean topology + UVs in seconds, the procedural ceiling).
Strengths: editability, tiny assets, style control, engine-ready.
Weakness: complex organics.

## Camp C — Reconstruction + retopo afterwards
Commercial image/text→3D with cleanup: **Tripo** Smart Mesh (clean
quad-dominant in ~2s), CSM Cube 2 (game-ready topology focus), Meshy 5,
Rodin Gen-2 (best textures, worst mesh repair burden). Classic offline:
QuadRemesher/ZRemesher/QuadWild. Hard limit everyone cites: automatic
retopo doesn't understand FUNCTION — "it doesn't know the character
needs a loop around the mouth to smile".

## Camp D — Hybrid human-in-the-loop (this skill's staged workflow)
**Kaedim**: AI draft + human artists refine, sold as a service
($400+/mo) — market validation that the hybrid staged pipeline IS the
production-grade answer.

## Rigging / animation state
**UniRig** (SIGGRAPH 2025, VAST/Tripo, open on GitHub): GPT-like
skeleton-tree tokenization + bone-point cross-attention skinning;
Rig-XL dataset (14k rigged models); beats commercial auto-riggers.
Candidate for our STAGE 3 on arbitrary meshes. Tripo/Meshy auto-rig +
auto walk/run clips; Anything World for animation.

## Empirical: Cube 3D on CPU (tested 2026-07 in this environment)
Runs end-to-end on 4 cores / 15GB RAM: ~10 min/asset including the 7GB
model load (CLIP text encoder auto-downloads from HF; pymeshlab absent →
postprocess skipped; marching cubes falls back to skimage). Verdict at
resolution_base 4.0: SHAPE understanding is real (a barrel with stave
hints), but the mesh is triangulated marching-cubes output — all tris,
zero edge flow, lumpy surface. Below this skill's procedural quality for
anything buildable by code. Cube/Hunyuan-class shape models only pay off
for ORGANICS, at high resolution, followed by MeshAnything-style artist
topology conversion — a GPU (e.g. RunPod, API reachable from here)
combo: shape gen → artist-mesh conversion → this skill's stages 2–4.

## Empirical: Cube 3D on RunPod GPU (tested 2026-07, RTX 3090)
Full quality run at resolution_base 8.0 (vs 4.0 on CPU): ~26s token
generation + ~7s geometry extraction per asset; whole pod lifecycle
(boot → pip → 7GB weights → 2 assets → fetch → auto-terminate) ≈ 9 min,
total cost ≈ $0.05/run. Results:
- **Creature** ("stylized cartoon dragon, big head, chunky body"):
  269,852 tris. DESIGN is genuinely good — coherent chibi proportions,
  horns/spikes/tail all intentional. The model designs like a stylist;
  only the tessellation is wrong.
- **Barrel**: 548,750 tris that read as a clean low-poly barrel
  over-tessellated — confirming Cube emits near-low-poly DESIGNS through
  a dense marching-cubes surface.
- **Decimation test**: Blender DECIMATE to 3,000 tris + shade_smooth
  (40°) preserved the creature's silhouette and features — already a
  usable stage-1 blockout at game budget without MeshAnything. Proper
  path for hero assets remains artist-mesh conversion on GPU.
Verdict: GPU generation JUSTIFIES for organics (creatures, characters,
nature props) as a stage-1 supplier: Cube shape → decimate (fast path)
or MeshAnything (quality path) → this skill's stages 2–4. Hard-surface
props stay procedural (our topology-by-construction beats decimated
marching cubes there).

## Empirical: MeshAnything V2 on RunPod GPU (tested 2026-07, RTX 4090)
Full pipeline proven end-to-end (pc_normal 8192 pts of the Cube creature
→ 613-face artist mesh in ~150s), but the RESULT is unusable for complex
organics: fragmented, non-watertight shards — tail with spikes survived,
body/head mostly missing. This is the documented V2 limitation (1600-face
cap; input must be representable in few faces), not a pipeline bug.
VERDICT: for creatures, the production path is **Cube3D → DECIMATE
(~3.5k tris) + shade_smooth → skill stages** — the decimated base kept
every feature and took a full texture/rig pass cleanly. Keep MA V2 only
as a candidate for simple single-mass props, or revisit with
MeshAnything-class successors trained with higher face caps.
Two hard-won compat notes: the flash-attn requirement is real — install
the PREBUILT wheel from Dao-AILab GitHub releases (cu12/torch2.4/cp311,
seconds, no nvcc); an eager-attention rewrite generated NaN faces (one
surviving triangle) despite RC=0 — silently-degenerate output, so always
assert output size, not just exit code.

## Empirical: Hunyuan3D-2 on RunPod GPU (tested 2026-07, RTX 4090) — WINNER
Image-to-3D from the APPROVED CONCEPT ART (not a text prompt) — closes
the concept-first loop: the mesh comes back faithful to the sheet.
Fed the dragon concept (gpt-image-1 output, rembg in-pod): 938k-tri
sculpt with EYES+eyelids, brow ridges, carved smile, nostrils, belly
button, individual fingers/toes — every face feature Cube3D lacked.
~2 min generation incl. 5GB weight download; whole pod ≈ 4 min ≈ $0.05.
Production recipe: decimate to ~12k tris (6k eats the eye topology) +
shade_smooth 42° → thin-feature masks + belly ellipse + majority-vote
border smoothing → EYES AS DECALS (flattened dark spheres snapped to the
eyeball bulges via a front raycast-grid apex finder — face-painting the
eye region gives blotchy borders at any budget) → painted_bake → spatial
groups + smoothed weights rig. Thin tail fins tolerate ~20° of summed
lateral bend across the 3-bone chain; beyond that they shear.
Compat: pin transformers==4.44.2 (torch 2.4 DTensor trap AGAIN),
apt install libgl1 (pymeshlab hard-imports libGL in Hunyuan, unlike
Cube's soft import), shapegen needs NO custom CUDA compile (texgen does —
skip it, our texture ladder is better for stylized anyway).
LICENSE: Hunyuan3D-2.0 is NON-COMMERCIAL; 2.1 ships a community license
(commercial-friendlier, MAU threshold) — for a commercial game, use 2.1
or keep Cube3D (Apache-ish CUBE license) as the safe supplier.
Supplier ranking for organics: Hunyuan3D-2 (concept image) > Cube3D
(text) >> MeshAnything V2 (fragmented).

## Empirical: Hunyuan3D-2mv MULTIVIEW (tested 2026-07, RTX 4090) — the pipeline
The open-source MV model takes up to 4 views with FIXED keys
front/left/back/right (dict input; view order = front, +90° cw, back,
+270°). Feeding 4 gpt-image-2 views generated from the approved concept
(one edits call per view; spell out expression/feature consistency in
each prompt) at octree_resolution=512 (~1.27M tris ≈ the site's
"1.5M faces" mode) produced the best mesh of every test: fully
symmetric, clean single spike row, sculpted eye sockets, individual
claws. Generation ~3 min on a 4090 (~$0.04). gpt-image-2 view quality
is far above gpt-image-1 (near mirror-perfect profiles) — use it for
all concept/view generation.
**Retopology**: Hunyuan3D-PolyGen 1.5 (the site's "polymesh" tool) has
NO open weights (unanswered community request, July 2025) — available
only via 3d.hunyuan.tencent.com and the Scenario platform. The local
stand-in is Blender's built-in **QuadriFlow** (`quadriflow_remesh`):
pre-decimate the dense mesh to ~250k tris, then target_faces≈9000 with
mesh symmetry → pure-quad uniform topology (7.2k quads on the dragon,
zero triangles, all features held). Not PolyGen's feature-aligned edge
loops, but real game topology: deformation-ready and subdividable —
replaces triangle decimation as the standard retopo stage.
**Hunyuan3D-Paint multiview ON the retopo mesh** (round 21, WORKS):
the full site workflow is now reproducible open-source — MV shape →
QuadriFlow quads → Paint turbo conditioned on the same gpt-image-2
views (front/left/back list, example order) → textured GLB with painted
eyes/iris, belly segments, shaded claws. Requires the DEVEL pytorch
image (nvcc): compile custom_rasterizer (CUDAExtension,
TORCH_CUDA_ARCH_LIST=8.9) + differentiable_renderer mesh_processor;
pip adds diffusers==0.32.0 + xatlas on top of the shape stack. On a
fast SECURE 4090 the whole round ran in ~5 min (~$0.06). Paint
re-unwraps via xatlas (quad input comes back ~14k tris) and its atlas
gutter is thin — strong pose deformation exposes seam texels; dilate
the atlas or keep bends inside the tested range. License caveat applies
(2.0 non-commercial; 2.1 for production).
**Reference-driven feature placement** (new core technique): geometry
probes for eye placement kept latching onto the muzzle (most-protruding
≠ feature). Instead, READ the front reference view: threshold the two
big dark clusters on the upper face, map image→mesh coords via the two
character bounding boxes (both normalized identically), raycast
front-to-back at that (x, z) for the surface point+normal, place the
decal there. The reference sheet knows WHERE features are; the mesh
only answers the surface question.

### RunPod orchestration pattern (hard-won, reuse verbatim)
1. GraphQL `podFindAndDeployOnDemand` with an OFFICIAL runpod/pytorch
   image (community images may never start; devel images too big).
2. Those images lack git/curl — fetch everything with python urllib
   (repo tarballs, weights via huggingface_hub).
3. Put the ENTIRE boot script in base64 and decode inside the pod
   (`echo B64 | base64 -d | python3 -`) — kills all shell-quoting bugs
   in dockerArgs (json-in-bash quotes caused a crash-loop).
4. Write `status.txt` after every step and serve the workdir with
   `python -m http.server 8000` → poll via
   `https://{podId}-8000.proxy.runpod.net/status.txt`.
5. Wrap each generation in subprocess with capture_output and dump
   stdout/stderr to `err-{name}.txt` — fetch it BEFORE terminating, or
   failures are undebuggable (a truncated CalledProcessError cost a
   round).
6. Pin transformers==4.44.2 for torch 2.4 images (newer transformers
   imports DTensor, torch≥2.5 only).
7. Monitor script polls status, fetches artifacts on done/fail, then
   ALWAYS terminates the pod (deadline-bounded) — no orphan billing.
8. **GPU fail-fast**: first boot step is `assert torch.cuda.is_available()`.
   A "SECURE" machine shipped with no CUDA and silently ran Cube on CPU
   for 32 min until the monitor deadline killed it; the assert turns that
   into a 30-second $0.01 failure. If redeploy lands on the same broken
   machineId, switch gpuTypeId — RunPod keeps assigning the only free unit.
9. **Getting input files INTO a pod**: dockerArgs rejects large payloads
   (~160KB base64 embed → GraphQL Internal Server Error), public drop
   hosts are dead to datacenter traffic (tmpfiles.org 403s from the pod,
   0x0.st/catbox closed uploads entirely), and private-repo raw URLs need
   tokens. The reliable pattern: the pod serves its own upload endpoint —
   boot starts a ThreadingHTTPServer whose do_PUT writes the body to disk
   (GET keeps serving status/results), sets status 'await-pc' and waits;
   the local monitor sees that status and curl -T PUTs the file through
   https://{podId}-8000.proxy.runpod.net. No third party involved.
10. MeshAnythingV2 on stock pytorch images: stub mesh2sdf (no wheel, only
   needed for --mc), and patch flash-attn to eager — replace
   `"flash_attention_2"`→`"eager"` + drop `use_flash_attention_2=True` /
   `to_bettertransformer()` in meshanything_v2.py, and in shape_opt.py
   replace the "Only flash_attention_2" raise with a
   `_prepare_4d_causal_attention_mask` call (transformers 4.39).

## What this skill should borrow next
1. MeshAnything-style conditioning as a bridge: image-to-3D for organic
   blockouts → artist-mesh conversion → our texture/rig/anim stages.
2. LL3M's BlenderRAG idea (docs-grounded API recall) + explicit
   multi-agent critique separation.
3. UniRig for stage-3 rigging of non-part-based meshes.
4. Our defensible niche (nobody else combines): topology-by-construction
   + stylized texture ladder + measured fitting/verification probes +
   human-gated stages.
