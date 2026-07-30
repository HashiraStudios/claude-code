"""Cel-shaded (anime cartoon) render of a painted GLB.

  blender -b --python toon_render.py -- <painted.glb> <outdir> [name]

The pipeline's paint stage delivers a PBR-textured GLB; this converts the
look to anime WITHOUT touching the asset: the baked basecolor texture is
kept as the flat colour, lighting is quantised into hard bands, and
Freestyle draws the ink lines. The GLB itself stays PBR — engines apply
their own toon shader; this render is the art-direction reference.

Per material:  Diffuse -> Shader to RGB -> CONSTANT ColorRamp -> multiply
by the basecolor texture -> Emission. Shader-to-RGB is EEVEE-only, and
colour management must be Standard — AgX smears the flat bands back into
gradients, defeating the style.
"""
import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
NAME = argv[2] if len(argv) > 2 else "toon"
os.makedirs(OUT, exist_ok=True)

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
obj = max(meshes, key=lambda o: len(o.data.polygons))
for o in meshes:
    if o is not obj:
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
lo = Vector((min(v[i] for v in bb) for i in range(3)))
hi = Vector((max(v[i] for v in bb) for i in range(3)))
s = 1.0 / max((hi - lo).z, 1e-6)
obj.scale = (s, s, s)
bpy.context.view_layer.update()
bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
lo = Vector((min(v[i] for v in bb) for i in range(3)))
hi = Vector((max(v[i] for v in bb) for i in range(3)))
obj.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# ---- convert every material to toon, keeping its basecolor image
for slot in obj.material_slots:
    m = slot.material
    if not m or not m.use_nodes:
        continue
    img = None
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image:
            img = n.image
            break
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = 'MULTIPLY'
    mul.inputs["Fac"].default_value = 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = 'CONSTANT'
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.38, 0.38, 0.42, 1)
    e[1].position, e[1].color = 0.32, (0.72, 0.72, 0.74, 1)
    e.new(0.65).color = (1.0, 1.0, 1.0, 1)
    e.new(0.92).color = (1.22, 1.22, 1.22, 1)
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    dif.inputs["Color"].default_value = (1, 1, 1, 1)
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    nt.links.new(s2r.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], mul.inputs["Color1"])
    if img:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.links.new(tex.outputs["Color"], mul.inputs["Color2"])
    else:
        mul.inputs["Color2"].default_value = (0.75, 0.75, 0.75, 1)
    nt.links.new(mul.outputs[0], emit.inputs["Color"])
    nt.links.new(emit.outputs[0], out.inputs["Surface"])

# ---- stage
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
sc.render.resolution_x = sc.render.resolution_y = 900
sc.eevee.taa_render_samples = 32
sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.82, 0.85, 0.90, 1)

sc.render.use_freestyle = True
vl = bpy.context.view_layer
vl.use_freestyle = True
fs = vl.freestyle_settings
ls = fs.linesets.new("ink") if not fs.linesets else fs.linesets[0]
ls.select_silhouette = True
ls.select_border = True
ls.select_crease = True
fs.crease_angle = math.radians(115)
ls.linestyle.color = (0.05, 0.04, 0.06)
ls.linestyle.thickness = 2.4

key = bpy.data.lights.new("K", 'SUN')
key.energy = 3.0
ko = bpy.data.objects.new("K", key)
sc.collection.objects.link(ko)
ko.rotation_euler = (math.radians(58), 0, math.radians(38))
fill = bpy.data.lights.new("F", 'SUN')
fill.energy = 1.0
fo = bpy.data.objects.new("F", fill)
sc.collection.objects.link(fo)
fo.rotation_euler = (math.radians(72), 0, math.radians(-130))

cam = bpy.data.objects.new("C", bpy.data.cameras.new("C"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 68
center = Vector((0, 0, 0.5))
span = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
for view, d in {"hero": (-0.75, -1, 0.35), "front": (0, -1, 0.06),
                "side": (-1, -0.08, 0.06), "back": (0.5, 1, 0.25)}.items():
    v = Vector(d).normalized()
    cam.location = center + v * span * 2.4
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, f"{NAME}_{view}")
    bpy.ops.render.render(write_still=True)
    print(f"[TOON] {NAME}_{view}.png")
print("TOON DONE")
