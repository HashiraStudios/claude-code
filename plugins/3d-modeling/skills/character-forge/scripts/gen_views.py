#!/usr/bin/env python3
"""Concept + 4 orthographic views via gpt-image-2.

  python gen_views.py --prompt "frog mecha, Brawl Stars style" --out work/frog
  python gen_views.py --reference ref.jpg --prompt "original character inspired by this" --out work/kid

Writes <out>/concept.png and <out>/views/{front,left,back,right}.png.
Requires OPENAI_API_KEY. Views are what the shape model sees — inspect
them before spending GPU time (the QA gate that matters most)."""
import argparse, base64, json, os, sys, urllib.request

API = "https://api.openai.com/v1/images"
KEY = os.environ.get("OPENAI_API_KEY") or sys.exit("set OPENAI_API_KEY")

VIEW_SPECS = {
    "front": "straight-on FRONT view, facing the camera directly, symmetrical stance, arms relaxed at the sides",
    "left": "straight-on LEFT SIDE profile view: the camera sees the character's LEFT side, the character faces LEFT",
    "back": "straight-on BACK view: seen from directly behind; describe ONLY back features — never repeat front-only features (no face, no front mouth) — smooth back surfaces where the front has openings",
    "right": "straight-on RIGHT SIDE profile view: the camera sees the character's RIGHT side, the character faces RIGHT",
}
BASE_STYLE = ("Full body, whole character fully visible with margin, feet on the "
              "ground, strictly orthographic with no perspective, plain pure white "
              "background, no text, no labels, no shadows, same colors, same "
              "expression and same proportions as the input character")

# Vehicles and props need their own view language: the character wording
# ("arms at the sides", "same expression", "no face on the back") either
# means nothing here or actively misleads the generator.
VIEW_SPECS_VEHICLE = {
    "front": "straight-on FRONT view: the camera is directly in front of the vehicle, looking at the grille and headlights, perfectly symmetrical, both front wheels equally visible",
    "left": "straight-on LEFT SIDE profile view: the camera is level with the vehicle's left flank, the vehicle points LEFT, both left wheels fully visible and round",
    "back": "straight-on BACK view: the camera is directly behind the vehicle, showing ONLY rear features — tailgate, rear bumper, tail lights, spare wheel if present — never a grille or headlights",
    "right": "straight-on RIGHT SIDE profile view: the camera is level with the vehicle's right flank, the vehicle points RIGHT, both right wheels fully visible and round",
}
BASE_STYLE_VEHICLE = ("The whole vehicle fully visible with margin, wheels resting on "
                      "the ground line, strictly orthographic with no perspective and "
                      "no camera tilt, plain pure white background, no text, no labels, "
                      "no logos, no badges, no shadows, exactly the same colors, "
                      "proportions and details as the input vehicle")


# A KIT part is generated alone so it gets the whole resolution budget.
# It has no ground contact and no host object — saying "feet on the
# ground" or "the whole vehicle" here produces a part welded to a car.
VIEW_SPECS_PART = {
    "front": "straight-on FRONT view of the part, centred, its mounting face toward the camera",
    "left": "straight-on LEFT SIDE view of the part, exact 90-degree profile. If the part is flat or blade-like this view is a GENUINELY NARROW EDGE-ON SLIVER — the thin spine toward the camera, only a fraction as wide as the front view — never a bent version and never the front view repeated. The part keeps EXACTLY the same straight alignment as the front view",
    "back": "straight-on BACK view of the part: the mounting/hidden side, showing brackets, bolts or hollow backing — never repeat the front face",
    "right": "straight-on RIGHT SIDE view of the part, exact 90-degree profile. If the part is flat or blade-like this view is a GENUINELY NARROW EDGE-ON SLIVER — the thin spine toward the camera, only a fraction as wide as the front view — never a bent version and never the front view repeated. The part keeps EXACTLY the same straight alignment as the front view",
}
BASE_STYLE_PART = ("ONLY this single isolated component, floating and complete, "
                   "detached from any vehicle or character, nothing else in frame, "
                   "filling most of the frame, strictly orthographic with no "
                   "perspective, plain pure white background, no ground, no shadow, "
                   "no text, no labels, no logos, exactly the same colors and "
                   "materials as the input")


def _multipart(fields, files):
    boundary = "----charforge"
    out = b""
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    for k, (fn, data) in files.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\n"
                f"Content-Type: image/png\r\n\r\n").encode() + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def call(endpoint, fields, files=None, retries=2):
    for attempt in range(retries + 1):
        try:
            if files:
                body, ctype = _multipart(fields, files)
                req = urllib.request.Request(f"{API}/{endpoint}", data=body,
                                             headers={"Authorization": f"Bearer {KEY}",
                                                      "Content-Type": ctype})
            else:
                req = urllib.request.Request(f"{API}/{endpoint}",
                                             data=json.dumps(fields).encode(),
                                             headers={"Authorization": f"Bearer {KEY}",
                                                      "Content-Type": "application/json"})
            d = json.loads(urllib.request.urlopen(req, timeout=300).read())
            if "error" in d:
                raise RuntimeError(d["error"].get("message", "api error"))
            return base64.b64decode(d["data"][0]["b64_json"])
        except Exception as e:
            if attempt == retries:
                raise
            print(f"  retry ({e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--reference", help="optional reference image to condition on")
    ap.add_argument("--out", required=True)
    ap.add_argument("--views-only", action="store_true",
                    help="skip concept generation, reuse <out>/concept.png")
    ap.add_argument("--only", help="regenerate a single view (front/left/back/right)")
    ap.add_argument("--kind", choices=["character", "vehicle", "part"], default="character",
                    help="which view language to use; vehicles/props are not characters")
    args = ap.parse_args()
    specs = {"vehicle": VIEW_SPECS_VEHICLE, "part": VIEW_SPECS_PART}.get(
        args.kind, VIEW_SPECS)
    style = {"vehicle": BASE_STYLE_VEHICLE, "part": BASE_STYLE_PART}.get(
        args.kind, BASE_STYLE)
    subject = {"vehicle": "vehicle", "part": "component"}.get(args.kind, "character")
    # a car is wider than it is tall; the portrait concept canvas that suits
    # a standing character wastes half the frame on one
    concept_size = "1024x1024" if args.kind == "part" else (
        "1536x1024" if args.kind == "vehicle" else "1024x1536")
    os.makedirs(f"{args.out}/views", exist_ok=True)
    concept_path = f"{args.out}/concept.png"

    if not args.views_only:
        print("concept...")
        if args.reference:
            data = call("edits", {"model": "gpt-image-2", "prompt": args.prompt,
                                  "size": concept_size, "n": "1"},
                        {"image[]": ("ref.png", open(args.reference, "rb").read())})
        else:
            data = call("generations", {"model": "gpt-image-2", "prompt": args.prompt,
                                        "size": concept_size, "n": 1})
        open(concept_path, "wb").write(data)
        print(f"  -> {concept_path} ({len(data)} bytes)")

    ref = open(concept_path, "rb").read()
    views = [args.only] if args.only else list(specs)
    for v in views:
        print(f"view {v}...")
        p = (f"Render this exact {subject}. VIEW: {specs[v]}. {style}")
        data = call("edits", {"model": "gpt-image-2", "prompt": p,
                              "size": "1024x1024", "n": "1"},
                    {"image[]": ("concept.png", ref)})
        open(f"{args.out}/views/{v}.png", "wb").write(data)
        print(f"  -> views/{v}.png ({len(data)} bytes)")
    print("DONE — inspect the views before running the shape stage.")


if __name__ == "__main__":
    main()
