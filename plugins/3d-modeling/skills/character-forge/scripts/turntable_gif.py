#!/usr/bin/env python3
"""360-degree GIF preview — the standard Character Forge deliverable.

  python turntable_gif.py <model.glb> <out.gif> [frames=36]

Drives headless Blender to render the frames (EEVEE, beauty light rig,
512px), then assembles an adaptive-palette GIF with Pillow.
Requires: blender on PATH, `pip install pillow`."""
import os, subprocess, sys, tempfile, textwrap

SRC = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2])
N = int(sys.argv[3]) if len(sys.argv) > 3 else 36

frames_dir = tempfile.mkdtemp(prefix="tt_")
blender_script = textwrap.dedent(f"""
    import bpy, math
    from mathutils import Vector
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    if "{SRC}".endswith('.glb'):
        bpy.ops.import_scene.gltf(filepath="{SRC}")
    else:
        bpy.ops.wm.obj_import(filepath="{SRC}", forward_axis='NEGATIVE_Z', up_axis='Y')
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    s = 1.0 / max(hi.z - lo.z, 1e-6)
    obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(v[i] for v in bb) for i in range(3)))
    hi = Vector((max(v[i] for v in bb) for i in range(3)))
    obj.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.eevee.taa_render_samples = 24
    world = bpy.data.worlds.new("W"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.92, 0.90, 1)
    scene.world = world
    key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", 'SUN'))
    key.data.energy = 3.0
    key.rotation_euler = (math.radians(50), 0, math.radians(-35))
    bpy.context.collection.objects.link(key)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    center = Vector((0, 0, 0.5))
    d = Vector((-0.75, -1.0, 0.45)).normalized()
    cam.location = center + d * 1.9
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    for i in range({N}):
        obj.rotation_euler = (0, 0, 2 * math.pi * i / {N})
        scene.render.filepath = "{frames_dir}/f%03d.png" % i
        bpy.ops.render.render(write_still=True)
    print("FRAMES DONE")
""")
sp = os.path.join(frames_dir, "render.py")
open(sp, "w").write(blender_script)
env = dict(os.environ, LIBGL_ALWAYS_SOFTWARE="1")
r = subprocess.run(["blender", "--background", "--python", sp],
                   capture_output=True, text=True, env=env, timeout=1800)
if "FRAMES DONE" not in r.stdout:
    sys.exit("blender render failed:\n" + r.stdout[-2000:] + r.stderr[-1000:])

from PIL import Image
import glob
frames = [Image.open(p).convert('P', palette=Image.ADAPTIVE, colors=256)
          for p in sorted(glob.glob(f"{frames_dir}/f*.png"))]
frames[0].save(OUT, save_all=True, append_images=frames[1:],
               duration=80, loop=0, optimize=True)
print(f"GIF -> {OUT} ({os.path.getsize(OUT)} bytes, {len(frames)} frames)")
