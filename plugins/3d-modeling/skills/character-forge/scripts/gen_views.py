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
    args = ap.parse_args()
    os.makedirs(f"{args.out}/views", exist_ok=True)
    concept_path = f"{args.out}/concept.png"

    if not args.views_only:
        print("concept...")
        if args.reference:
            data = call("edits", {"model": "gpt-image-2", "prompt": args.prompt,
                                  "size": "1024x1536", "n": "1"},
                        {"image[]": ("ref.png", open(args.reference, "rb").read())})
        else:
            data = call("generations", {"model": "gpt-image-2", "prompt": args.prompt,
                                        "size": "1024x1536", "n": 1})
        open(concept_path, "wb").write(data)
        print(f"  -> {concept_path} ({len(data)} bytes)")

    ref = open(concept_path, "rb").read()
    views = [args.only] if args.only else list(VIEW_SPECS)
    for v in views:
        print(f"view {v}...")
        p = (f"Render this exact character. VIEW: {VIEW_SPECS[v]}. {BASE_STYLE}")
        data = call("edits", {"model": "gpt-image-2", "prompt": p,
                              "size": "1024x1024", "n": "1"},
                    {"image[]": ("concept.png", ref)})
        open(f"{args.out}/views/{v}.png", "wb").write(data)
        print(f"  -> views/{v}.png ({len(data)} bytes)")
    print("DONE — inspect the views before running the shape stage.")


if __name__ == "__main__":
    main()
