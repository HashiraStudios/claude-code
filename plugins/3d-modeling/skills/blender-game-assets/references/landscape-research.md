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

## What this skill should borrow next
1. MeshAnything-style conditioning as a bridge: image-to-3D for organic
   blockouts → artist-mesh conversion → our texture/rig/anim stages.
2. LL3M's BlenderRAG idea (docs-grounded API recall) + explicit
   multi-agent critique separation.
3. UniRig for stage-3 rigging of non-part-based meshes.
4. Our defensible niche (nobody else combines): topology-by-construction
   + stylized texture ladder + measured fitting/verification probes +
   human-gated stages.
