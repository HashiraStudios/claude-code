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

## What this skill should borrow next
1. MeshAnything-style conditioning as a bridge: image-to-3D for organic
   blockouts → artist-mesh conversion → our texture/rig/anim stages.
2. LL3M's BlenderRAG idea (docs-grounded API recall) + explicit
   multi-agent critique separation.
3. UniRig for stage-3 rigging of non-part-based meshes.
4. Our defensible niche (nobody else combines): topology-by-construction
   + stylized texture ladder + measured fitting/verification probes +
   human-gated stages.
