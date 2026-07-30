"""
Staged hybrid pipeline — human-in-the-loop checkpoints.

The skill's mature operating mode is NOT "generate a finished asset in
one shot"; it is a four-stage production pipeline where the human can
enter at every gate, edit in Blender, and hand back:

  STAGE 1 — BLOCKOUT (modeling)
    Agent: build the model with the construction/shape/anatomy stack.
    Deliverable: render_clay() views (matte gray + cavity edges + shadow
    — the review look artists expect) + stage_save('blockout').
    Human gate: open the .blend, adjust proportions, add details, save.

  STAGE 2 — TEXTURE
    Agent: stage_open() the (possibly edited!) .blend and RE-MEASURE —
    never assume script-built state: re-probe dimensions, bands and
    anchors before mapping, because the human may have moved anything.
    Then the texture ladder (trim / AI sheet / unique bake) + art
    direction. Deliverable: beauty renders + stage_save('textured').
    Human gate: adjust UVs/materials/colors, save.

  STAGE 3 — RIG
    Agent: armature + explicit per-part weights + WEIGHT VERIFICATION
    (empty-vert count) + bend test renders. stage_save('rigged').
    Human gate: fix weights, tweak bone placement.

  STAGE 4 — ANIMATION
    Agent: keyframed clips (idle/walk/action), playblast-style frame
    renders, final export (FBX/GLB, bake_anim as needed).

RESUME RULE: every stage begins by re-running the cheap verifications
(dimensions, attach probes, weight check) against the file it received —
the human's edits are welcome and the probes adapt the numbers; silent
assumptions about the previous stage are how hybrid pipelines break.
"""

import bpy
import os


def stage_save(name, dirpath=None, note=""):
    """Checkpoint the scene as a .blend the human can open, edit and hand
    back. Prints the handoff path; pack images so textures travel."""
    dirpath = dirpath or globals().get('OUT', '/mnt/user-data/outputs')
    path = os.path.join(dirpath, f"stage_{name}.blend")
    try:
        bpy.ops.file.pack_all()          # textures travel inside the file
    except RuntimeError as e:
        print(f"pack_all: {e} (continuing)")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print(f"[STAGE SAVED] {name}: {path}" + (f"  — {note}" if note else ""))
    return path


def stage_open(path):
    """Load a checkpoint .blend (the human may have edited it). ALWAYS
    re-probe measurements after opening — treat the file as foreign."""
    bpy.ops.wm.open_mainfile(filepath=path)
    objs = [o.name for o in bpy.data.objects if o.type == 'MESH']
    print(f"[STAGE OPENED] {path}: meshes={objs}")
    return objs
