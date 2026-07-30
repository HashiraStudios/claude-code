"""
AI-generated textures — plug an image generator into the trim pipeline.

Procedural synthesis has a quality ceiling ("too stiff"). The production
answer is to source the SURFACES from an image generator (GPT-image /
fal.ai / Higgsfield / SDXL...) and let our pipeline handle everything the
generator can't: tiling, trim-sheet assembly, normal/rough derivation and
UV mapping.

DIVISION OF LABOR
  generator -> raw painted surface (wood, stone, plaster, shingles...)
  this module -> make_tileable() (crossfade wrap), assemble_trim() (resample
      sources into the STRIPS bands), then the existing stack: normal via
      normal_from_image(), roughness via build_rough_metal(), mapping via
      trim_map()/trim_swap()/trim_map_around().

PROMPTS (per material, tuned for hand-painted trim use — generate at 1024,
1:1, then downscale; ask for edge-to-edge flat texture, no perspective):

  !! ONE PALETTE PER ASSET — the stiffness killer. Generating each material
  with its own implicit palette produces strips that never harmonize. Every
  prompt for one asset must share the SAME art-direction sentence:
    "ART DIRECTION: unified storybook palette of honey-ochre wood, warm
     cream plaster, terracotta and sage-teal accents; shadows are never
     gray or black, they shift toward saturated cool violet; highlights
     are warm and sun-kissed like color dodge; every element carries a
     soft painted gradient inside it (darker at its base, lighter on top);
     subtle hue variation everywhere so no two elements are the same
     color; loose confident brushwork, big readable shapes, painterly and
     soft, never mechanical or uniform"
  Then finish the pipeline with art-direction.py: stylize_grade() on the
  assembled sheet + vertex_gradient/vertex_ao/apply_grade on the objects.
  wood     "seamless tileable hand-painted stylized game texture, vertical
            wooden planks, warm brown, per-plank value variation, painted
            bright edge highlights, soft brush-stroke grain, subtle cracks,
            WoW/Riot hand-painted style, flat 2D orthographic, fills frame
            edge to edge, no perspective, no vignette, no lighting hotspot"
  stone    same header + "rounded stone blocks in offset courses, painted
            mortar shadows, edge highlights on top of each stone"
  plaster  same header + "clean warm plaster wall, very subtle patching and
            value variation, mostly smooth"
  shingles same header + "one row of wooden roof boards, vertical joints,
            per-board value variation"  (ONE row — multi-row strips seam
            when V-fitted across a roof slab)
  grass    same header + "stylized grass, soft painted clumps, vivid green"

GENERATOR ACCESS NOTES (session-dependent):
  * Higgsfield MCP `generate_image` — needs workspace credits.
  * OpenAI gpt-image (OPENAI_API_KEY) / fal.ai — need the environment's
    network policy to allow api.openai.com / fal.run.
  * Or a human generates externally and drops PNGs into the repo.
Once any route works: generate -> save PNGs -> make_tileable -> assemble.

VALIDATED END-TO-END with gpt-image-1 (1024px, quality=medium, ~40s each):
the per-material prompts above produced genuine hand-painted-grade surfaces
(painted wood grain with knots and cracked highlights, stone with painted
bevels and mortar) that the procedural pass could not reach. Assembled at
512 via assemble_trim, normal via normal_from_image(strength~1.6, normal
material strength ~0.8 — AI sheets carry painted shading already, so keep
the normal subtle), roughness per strip as usual.
"""

import bpy
import math


def _load_px(path):
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    return list(img.pixels), w, h


def make_tileable(path, out_path=None, blend=0.12):
    """Make an image seamlessly tileable in X and Y by crossfading each edge
    with the opposite side over `blend` fraction of the width/height.
    Generators rarely produce true tiles; this always does."""
    px, w, h = _load_px(path)
    bw = max(1, int(w * blend))
    out = px[:]
    for y in range(h):
        for k in range(bw):
            t = (k + 0.5) / bw / 2          # 0..0.5 toward the edge
            a = (y * w + k) * 4                       # left edge texel
            b = (y * w + (w - bw + k)) * 4            # matching right region
            for c in range(4):
                va, vb = px[a + c], px[b + c]
                out[a + c] = va * (0.5 + t) + vb * (0.5 - t)
                out[b + c] = vb * (0.5 + t) + va * (0.5 - t)
    px = out[:]
    bh = max(1, int(h * blend))
    for x in range(w):
        for k in range(bh):
            t = (k + 0.5) / bh / 2
            a = (k * w + x) * 4
            b = ((h - bh + k) * w + x) * 4
            for c in range(4):
                va, vb = px[a + c], px[b + c]
                out[a + c] = va * (0.5 + t) + vb * (0.5 - t)
                out[b + c] = vb * (0.5 + t) + va * (0.5 - t)
    img = bpy.data.images.new("Tileable", width=w, height=h, alpha=False)
    img.pixels = out
    if out_path:
        img.filepath_raw = out_path
        img.file_format = 'PNG'
        img.save()
    return img


def assemble_trim(sources, strips, name="AITrim", size=512, path=None):
    """Build a trim sheet from per-strip source images.
    `sources` = {strip_name: image_path}; `strips` = STRIPS dict from
    trim-sheet.py ((y0,y1) pixel rows in the 256 layout). Each source is
    resampled (bilinear) to its band — X spans the full sheet so U tiling
    is preserved from the (tileable) source."""
    out = [0.0] * (size * size * 4)
    for sname, (sy0, sy1) in strips.items():
        if sname not in sources:
            continue
        spx, sw, sh = _load_px(sources[sname])
        y0, y1 = int(sy0 / 256 * size), int(sy1 / 256 * size)
        band_h = max(1, y1 - y0)
        for y in range(y0, y1):
            fy = (y - y0) / band_h * (sh - 1)
            iy = int(fy)
            ty = fy - iy
            for x in range(size):
                fx = x / size * (sw - 1)
                ix = int(fx)
                tx = fx - ix
                i00 = (iy * sw + ix) * 4
                i10 = (iy * sw + min(sw - 1, ix + 1)) * 4
                i01 = (min(sh - 1, iy + 1) * sw + ix) * 4
                i11 = (min(sh - 1, iy + 1) * sw + min(sw - 1, ix + 1)) * 4
                o = (y * size + x) * 4
                for c in range(3):
                    top = spx[i00 + c] * (1 - tx) + spx[i10 + c] * tx
                    bot = spx[i01 + c] * (1 - tx) + spx[i11 + c] * tx
                    out[o + c] = top * (1 - ty) + bot * ty
                out[o + 3] = 1.0
    img = bpy.data.images.new(name, width=size, height=size, alpha=False)
    img.pixels = out
    if path:
        img.filepath_raw = path
        img.file_format = 'PNG'
        img.save()
    return img
