"""360° turntable preview as MP4 (H.264) — the standard deliverable.

  blender --background --python preview_video.py -- <model.glb> <out.mp4> [frames=48]

Blender ships its own FFMPEG encoder, so this needs NO system ffmpeg.
MP4 plays everywhere; GIF is a poor fallback (large, and some viewers
refuse to animate it)."""
import bpy, sys, math, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
N = int(argv[2]) if len(argv) > 2 else 48
RES, FPS = 640, 24

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
if SRC.lower().endswith((".glb", ".gltf")):
    bpy.ops.import_scene.gltf(filepath=SRC)
else:
    bpy.ops.wm.obj_import(filepath=SRC, forward_axis='NEGATIVE_Z', up_axis='Y')
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
scene.render.fps = FPS
scene.render.resolution_x = scene.render.resolution_y = RES
scene.eevee.taa_render_samples = 16
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.92, 0.90, 1)
scene.world = world
key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", 'SUN'))
key.data.energy = 3.2
key.rotation_euler = (math.radians(52), 0, math.radians(-38))
bpy.context.collection.objects.link(key)
fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", 'SUN'))
fill.data.energy = 1.1
fill.rotation_euler = (math.radians(65), 0, math.radians(140))
bpy.context.collection.objects.link(fill)
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
bpy.context.collection.objects.link(cam)
scene.camera = cam
center = Vector((0, 0, 0.55))
d = Vector((-0.72, -1.0, 0.34)).normalized()
cam.location = center + d * 2.1
cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()

obj.rotation_mode = 'XYZ'
for f, deg in ((1, 0.0), (N, 2 * math.pi)):
    obj.rotation_euler = (0, 0, deg)
    obj.keyframe_insert('rotation_euler', frame=f)
for fc in obj.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'LINEAR'

scene.frame_start, scene.frame_end = 1, N
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'HIGH'
scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
scene.render.filepath = OUT
bpy.ops.render.render(animation=True)
real = OUT if os.path.exists(OUT) else f"{OUT}0001-{N:04d}.mp4"
print(f"PREVIEW -> {real} ({os.path.getsize(real) if os.path.exists(real) else 0} bytes)")
