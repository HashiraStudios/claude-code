---
name: blender-game-assets
description: Complete workflow for creating optimized, game-ready 3D assets in Blender via MCP. Covers goal-driven modeling with executable bpy/bmesh construction recipes, a mandatory multi-view visual critique loop, reference-driven & real-scale modeling, hard-surface vs organic topology, low-poly modeling, UV unwrapping, retopology, vertex painting, Geometry Nodes, texture baking, and FBX export for Roblox Studio and Unreal Engine (UEFN). Use for building props, characters, environments, and procedural assets — especially when the goal is to CONSTRUCT quality geometry, not just generate it.
---

# Blender Game Assets Production

Professional workflow for building optimized game assets with Blender MCP.
Focused on Roblox Studio and Unreal Engine (UEFN) pipelines with FBX export.

## Read this first: how an agent actually models

You construct geometry by **running Python**, not by pressing hotkeys. Any guide
that says "use Ctrl+R / E / B" is describing a human UI you cannot drive. This
skill instead gives you **executable, parameterized recipes**. The mindset:

1. **Start from the goal, not the menu.** Name the object, match it to a form
   archetype, follow that recipe chain. → `references/goal-to-technique.md`
2. **Block out coarse → fine.** Massing at real scale first; detail last, only
   where the camera sees. Approve the silhouette before spending polygons.
3. **LOOK and iterate.** Build → render multiple views → critique honestly →
   fix → repeat. Two clean passes minimum. → `references/topology-and-critique.py`
4. **Model to spec.** Real dimensions in meters, scale applied to 1.0, tri
   budget respected. Measure with `report()`, don't eyeball.

The reference files are the core of the modeling capability — load and use them:

| File | What it gives you |
|---|---|
| `references/modeling-recipes.py` | Executable bpy/bmesh construction ops: box, cylinder, extrude, inset, bevel, loop cut, bridge, lathe/spin, mirror/array/solidify modifiers, measurement helpers. **Paste these into `execute_blender_code`.** |
| `references/goal-to-technique.md` | "What you want to make → which technique" map, real-scale table, hard-surface vs organic fork, the block-out method. |
| `references/topology-and-critique.py` | Reference-image setup, real-scale matching, multi-view render (`render_turntable`), and the `critique()` checklist. |

---

## Core Workflow

### 1. Scene Setup & Assessment

**Always start by checking the scene and setting real-world units:**

```python
blender:get_scene_info()
blender:get_viewport_screenshot(max_size=1024)
```

Set metric/meters before modeling (see `goal-to-technique.md` → "Real-scale first").

Check available integrations:

```python
blender:get_polyhaven_status()
blender:get_hyper3d_status()
blender:get_sketchfab_status()
```

### 2. Asset Sourcing Strategy

Decide up front: **build it** (best control/quality — use the recipes) vs
**source/generate a base** then refine.

**PolyHaven** (textures, HDRIs, models):
- Search: `blender:search_polyhaven_assets(asset_type="textures", categories="wood,metal")`
- Download: `blender:download_polyhaven_asset(asset_id="wood_planks", asset_type="textures", resolution="2k")`
- Apply: `blender:set_texture(object_name="Cube", texture_id="wood_planks")`

**Sketchfab** (base models):
- Search: `blender:search_sketchfab_models(query="low poly tree", downloadable=true, count=10)`
- Download: `blender:download_sketchfab_model(uid="model_uid")`

**Hyper3D Rodin** (AI generation — treat output as a *base* to retopo/clean, not final):
- Text-to-3D: `blender:generate_hyper3d_model_via_text(text_prompt="wooden crate with metal bands", bbox_condition=[1.0, 1.0, 1.2])`
- Image-to-3D: `blender:generate_hyper3d_model_via_images(input_image_paths=["/path/to/ref.jpg"])`
- Poll: `blender:poll_rodin_job_status(subscription_key="key")`
- Import: `blender:import_generated_asset(name="Crate", task_uuid="uuid")`

### 3. Reference-Driven Setup (when matching a real object or concept)

Load blueprints and lock scale before modeling — build to match, not from memory:

```python
# from references/topology-and-critique.py
load_reference("/path/to/front.png", axis='FRONT', size=2.0)
load_reference("/path/to/side.png",  axis='SIDE',  size=2.0)
# ...model...
match_scale(obj, target_dim_m=2.03, along='Z')   # e.g. a real door height
```

---

## Modeling (the executable way)

> Full recipe library: `references/modeling-recipes.py`.
> Which recipe for which object: `references/goal-to-technique.md`.

### Polygon Budgets
- **Mobile/Roblox decorative props**: 300–1000 tris
- **UEFN decorative props**: 500–2000 tris
- **Hero props close-up**: 2000–5000 tris
- **Characters (mobile)**: 3000–7500 tris
- **Characters (PC/console)**: 10000–20000 tris

Check with `tri_count(obj)` / `report(obj)` — don't guess.

### The recipes replace the hotkeys

| Human hotkey | Executable recipe (numeric, deterministic) |
|---|---|
| Add cube then scale | `add_box(name, size=(x,y,z))` — keeps scale 1.0 |
| `E` extrude | `extrude_faces(bm, faces, translate)` / `extrude_along_normal(bm, faces, dist)` |
| `I` inset | `inset_faces(bm, faces, thickness, depth)` |
| `Ctrl+B` bevel | `bevel_edges(bm, edges, offset, segments)` / `bevel_all_sharp(obj, angle_deg)` |
| `Ctrl+R` loop cut | `loop_cut(bm, faces, cuts)` |
| Bridge Edge Loops | `bridge(bm, edge_loops)` |
| Spin / Screw (lathe) | `spin_lathe(bm, profile_verts, axis, angle_deg, steps)` |
| Mirror / Array / Solidify | `add_mirror` / `add_array` / `add_solidify` / `add_bevel_modifier` |

Worked example — a beveled wooden crate at real scale (~600 tris):

```python
code = open("references/modeling-recipes.py").read() + '''

# Block out: a 0.6 m crate (scale stays 1.0)
crate = add_box("Crate", size=(0.6, 0.6, 0.6))

# Recessed panels on every side
bm = edit_begin(crate)
inset_faces(bm, list(bm.faces), thickness=0.06, depth=-0.015, individual=True)
edit_commit(bm, crate)

# Catch the light on every hard edge -> reads solid, not faceted
bevel_all_sharp(crate, angle_deg=40, offset=0.012, segments=2)

cleanup(crate)
report(crate)
'''
blender:execute_blender_code(code)
```

> The `open(...).read()` prelude loads the recipe functions into the exec
> namespace. Alternatively paste the specific functions you need inline.

### Modeling principles

**Hard-surface** (props, machines, architecture):
- Silhouette comes from **bevels catching light**, not density.
- Triangles/n-gons OK on **flat, non-deforming** faces.
- Support loops next to a bevel keep it crisp.
- Model half + `add_mirror` when symmetric.

**Organic** (anything that deforms/animates):
- **Quads only** in deforming zones.
- **Edge loops follow deformation** — rings at joints, loops around eyes/mouth.
- Keep poles off crease lines and out of high-deformation zones.
- Even quad density → even texel density → clean skinning.

Not sure which? Ask *does this surface ever bend?* — that picks the fork.
(Full detail in `goal-to-technique.md`.)

**Smooth shading without subdivision:**
```python
code = """
import bpy, math
obj = bpy.context.active_object
bpy.ops.object.shade_smooth()
# Auto-smooth via modifier (Blender 4.1+) or mesh flag (older):
if hasattr(obj.data, 'use_auto_smooth'):
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = math.radians(30)
else:
    bpy.ops.object.shade_auto_smooth(angle=math.radians(30))
"""
blender:execute_blender_code(code)
```

### 4. Mandatory Visual Critique Loop

**Do not proceed to UV until the model passes critique.** This is the step that
closes the gap between generated and built.

```python
code = open("references/topology-and-critique.py").read() + '''
obj = bpy.context.active_object
render_turntable(obj, name="crate")   # writes front/right/top/persp PNGs
critique()                             # prints the checklist
'''
blender:execute_blender_code(code)
```

Then **open the PNGs** with the file-reading tools and grade the *image* against
the checklist (silhouette, form, topology, budget, scale). Fix what fails and
re-render. Two clean passes = done.

---

## Retopology Workflow

Use when converting high-poly sculpts/scans/AI-generated bases to game-ready assets.

### Setup
```python
code = """
import bpy
high_poly = bpy.data.objects['HighPoly']
low_poly = bpy.data.objects['LowPoly']

shrink = low_poly.modifiers.new(name='Shrinkwrap', type='SHRINKWRAP')
shrink.target = high_poly
shrink.wrap_method = 'PROJECT'
shrink.use_project_z = True
shrink.use_positive_direction = True
shrink.use_negative_direction = True

bpy.context.scene.tool_settings.use_snap = True
bpy.context.scene.tool_settings.snap_elements = {'FACE'}
bpy.context.scene.tool_settings.use_snap_project = True
"""
blender:execute_blender_code(code)
```

### Best Practices
- Start with major edge loops (eyes, mouth, limbs).
- Maintain quad topology for animation.
- Use Mirror modifier for symmetrical objects.
- Target 1/10th to 1/20th polygon count of high-poly.
- Avoid poles (5+ edges) near deformation areas.
- Keep consistent polygon density (texel density).

### Baking Normal Maps
```python
code = """
import bpy
high_poly = bpy.data.objects['HighPoly']
low_poly = bpy.data.objects['LowPoly']

bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.bake_type = 'NORMAL'
bpy.context.scene.render.bake.use_selected_to_active = True
bpy.context.scene.render.bake.cage_extrusion = 0.1
bpy.context.scene.render.bake.max_ray_distance = 0.5

img = bpy.data.images.new('NormalMap', width=2048, height=2048)

high_poly.select_set(True)
low_poly.select_set(True)
bpy.context.view_layer.objects.active = low_poly

bpy.ops.object.bake(type='NORMAL')

img.filepath_raw = '/mnt/user-data/outputs/normal_map.png'
img.file_format = 'PNG'
img.save()
"""
blender:execute_blender_code(code)
```

## UV Unwrapping Excellence

### Golden Rules
1. **Every hard edge MUST be a UV seam** (prevents normal baking artifacts).
2. **Outer edges of UV shells must be straight** (prevents aliasing/staircasing).
3. **Align shells to U/V axes** (rotate only in 90° increments).
4. **Maintain uniform texel density** (consistent pixel-per-unit ratio).

### Texel Density Standards
- **Target**: 6–10 TD/cm for most assets
- **Minimum**: 5.12 TD/cm for distant objects
- **Formula**: Texture Resolution / Physical Size in cm

### UV Unwrapping Workflow
```python
code = """
import bpy, math
obj = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')

bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.mark_sharp(clear=True)
bpy.ops.mesh.edges_select_sharp(sharpness=math.radians(30))
bpy.ops.mesh.mark_seam()

bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
# Or, after seam marking:
# bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.02)

bpy.ops.object.mode_set(mode='OBJECT')
"""
blender:execute_blender_code(code)
```

### UV Layout Optimization
```python
code = """
import bpy
obj = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')

bpy.ops.uv.select_all(action='SELECT')
bpy.ops.uv.pack_islands(margin=0.01, rotate=True)

bpy.ops.object.mode_set(mode='OBJECT')
"""
blender:execute_blender_code(code)
```

### UV Checker Pattern
```python
code = """
import bpy
mat = bpy.data.materials.new('UV_Checker')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

checker = nodes.new('ShaderNodeTexChecker')
checker.inputs['Scale'].default_value = 8.0
output = nodes.new('ShaderNodeOutputMaterial')
links.new(checker.outputs['Color'], output.inputs['Surface'])

obj = bpy.context.active_object
if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)
"""
blender:execute_blender_code(code)
```

## Vertex Painting Techniques

Vertex painting adds color/variation without textures — efficient for low-poly games.

### Setup Vertex Colors
```python
code = """
import bpy
obj = bpy.context.active_object
if not obj.data.color_attributes:
    obj.data.color_attributes.new(name='Color', type='BYTE_COLOR', domain='POINT')
bpy.ops.object.mode_set(mode='VERTEX_PAINT')
"""
blender:execute_blender_code(code)
```

### Vertex Paint Shader
```python
code = """
import bpy
obj = bpy.context.active_object
mat = bpy.data.materials.new('VertexColor')
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

color_attr = nodes.new('ShaderNodeVertexColor')
color_attr.layer_name = 'Color'
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
output = nodes.new('ShaderNodeOutputMaterial')
links.new(color_attr.outputs['Color'], bsdf.inputs['Base Color'])
links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

if obj.data.materials:
    obj.data.materials[0] = mat
else:
    obj.data.materials.append(mat)
"""
blender:execute_blender_code(code)
```

### Vertex Painting Best Practices
- Higher vertex density = smoother gradients.
- Use for: dirt, wear, ambient occlusion, team colors, material masks.
- Combine with textures using Mix Shader (vertex color as mask).
- Roblox: SurfaceAppearance with ColorMap. UEFN: Vertex Color node in Material Editor.

## Geometry Nodes for Procedural Assets

Use for: scattered props, vegetation, modular buildings, arrays, instancing.

### Basic Asset Scattering
```python
code = """
import bpy
obj = bpy.context.active_object
modifier = obj.modifiers.new(name='GeoNodes', type='NODES')
node_group = bpy.data.node_groups.new('AssetScatter', 'GeometryNodeTree')
modifier.node_group = node_group
nodes = node_group.nodes
links = node_group.links

group_in = nodes.new('NodeGroupInput')
group_out = nodes.new('NodeGroupOutput')
distribute = nodes.new('GeometryNodeDistributePointsOnFaces')
distribute.distribute_method = 'POISSON'
instance = nodes.new('GeometryNodeInstanceOnPoints')
collection = nodes.new('GeometryNodeCollectionInfo')
collection.inputs['Collection'].default_value = bpy.data.collections.get('Props')
random_scale = nodes.new('FunctionNodeRandomValue')
random_scale.data_type = 'FLOAT_VECTOR'

links.new(group_in.outputs[0], distribute.inputs['Mesh'])
links.new(distribute.outputs['Points'], instance.inputs['Points'])
links.new(collection.outputs['Geometry'], instance.inputs['Instance'])
links.new(random_scale.outputs['Value'], instance.inputs['Scale'])
links.new(instance.outputs['Instances'], group_out.inputs[0])
"""
blender:execute_blender_code(code)
```

### Apply Geometry Nodes (Make Real)
```python
code = """
import bpy
obj = bpy.context.active_object
bpy.ops.object.convert(target='MESH')
bpy.ops.object.duplicates_make_real()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.join()
"""
blender:execute_blender_code(code)
```

### Performance Tips
- Apply GeoNodes before export.
- Use LOD for distant instances.
- Limit instance counts (Roblox: ~1000, UEFN: ~10000).
- Bake procedural textures to image textures.

## Texture Optimization

### Texture Size Guidelines
- **Roblox mobile**: 512×512 to 1024×1024
- **Roblox PC**: 1024×1024 to 2048×2048
- **UEFN mobile**: 1024×1024 to 2048×2048
- **UEFN PC/Console**: 2048×2048 to 4096×4096

### Texture Atlas Creation
```python
code = """
import bpy
objects = bpy.context.selected_objects
for obj in objects:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.transform.resize(value=(0.5, 0.5, 1.0))
    bpy.ops.transform.translate(value=(0.25, 0.25, 0.0))
    bpy.ops.object.mode_set(mode='OBJECT')
"""
blender:execute_blender_code(code)
```

## FBX Export Pipeline

### Roblox Studio Export
```python
code = """
import bpy
export_path = '/mnt/user-data/outputs/model_roblox.fbx'
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 0.01
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.fbx(
    filepath=export_path, use_selection=True, global_scale=1.0,
    apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
    object_types={'MESH', 'ARMATURE'}, use_mesh_modifiers=True,
    mesh_smooth_type='FACE', use_tspace=False, path_mode='COPY',
    embed_textures=True, axis_forward='-Y', axis_up='Z',
    bake_anim=False, add_leaf_bones=False,
)
"""
blender:execute_blender_code(code)
```

### Unreal Engine / UEFN Export
```python
code = """
import bpy
export_path = '/mnt/user-data/outputs/model_unreal.fbx'
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 0.01
for obj in bpy.context.selected_objects:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.export_scene.fbx(
    filepath=export_path, use_selection=True, global_scale=1.0,
    apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE',
    object_types={'MESH', 'ARMATURE'}, use_mesh_modifiers=True,
    mesh_smooth_type='FACE', use_tspace=True, use_custom_props=True,
    path_mode='COPY', embed_textures=True, axis_forward='-Y', axis_up='Z',
    primary_bone_axis='X', secondary_bone_axis='-Z',
    bake_anim=False, add_leaf_bones=False,
)
"""
blender:execute_blender_code(code)
```

### Pre-Export Checklist
```python
code = """
import bpy
def validate_for_export():
    issues = []
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            if tuple(obj.scale) != (1.0, 1.0, 1.0):
                issues.append(f"{obj.name}: Scale not applied")
            poly_count = len(obj.data.polygons)
            if poly_count > 20000:
                issues.append(f"{obj.name}: High poly count ({poly_count})")
            if not obj.data.uv_layers:
                issues.append(f"{obj.name}: Missing UVs")
            for poly in obj.data.polygons:
                if len(poly.vertices) > 4:
                    issues.append(f"{obj.name}: Contains n-gons")
                    break
    return issues

issues = validate_for_export()
print("Export Issues Found:" if issues else "✓ Ready for export")
for issue in issues:
    print(f"  - {issue}")
"""
blender:execute_blender_code(code)
```

## Advanced Techniques

### LOD (Level of Detail) Generation
```python
code = """
import bpy
obj = bpy.context.active_object
for lod_level in range(1, 4):
    bpy.ops.object.duplicate()
    lod_obj = bpy.context.active_object
    lod_obj.name = f"{obj.name}_LOD{lod_level}"
    decimate = lod_obj.modifiers.new(name='Decimate', type='DECIMATE')
    decimate.ratio = 1.0 / (2 ** lod_level)
    decimate.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier='Decimate')
"""
blender:execute_blender_code(code)
```

### Collision Mesh Generation
```python
code = """
import bpy
obj = bpy.context.active_object
bpy.ops.object.duplicate()
collision = bpy.context.active_object
collision.name = f"UCX_{obj.name}"
decimate = collision.modifiers.new(name='Decimate', type='DECIMATE')
decimate.ratio = 0.1
bpy.ops.object.modifier_apply(modifier='Decimate')
"""
blender:execute_blender_code(code)
```

## Performance Optimization Strategies

- **Draw calls**: combine objects sharing materials, use atlases, limit unique materials.
- **Polygon budget**: profile by importance, use LODs aggressively, reserve polys for hero assets.
- **Texture memory**: power-of-2 textures, in-engine compression, share textures, trim sheets.

## Workflow Summary

**Standard asset creation pipeline:**

1. **Concept** → references, real-scale units, check integrations (`goal-to-technique.md`).
2. **Block out** → massing at real dimensions (`add_box`/`add_cylinder`).
3. **Model** → executable recipes by archetype (`modeling-recipes.py`).
4. **Critique loop** → `render_turntable` + `critique()`, fix, repeat (≥2 clean passes).
5. **Retopology** → if starting from a high-poly/AI base.
6. **UV unwrapping** → following the golden rules.
7. **Texturing** → PolyHaven textures or vertex paint.
8. **Detail pass** → vertex colors, geometry nodes.
9. **Baking** → normal maps, AO.
10. **Validation** → poly count, UVs, scale (`report()` + pre-export checklist).
11. **Export** → platform-specific FBX.
12. **Testing** → import to target engine, iterate.

**Always provide downloadable outputs in `/mnt/user-data/outputs/`.**

## Common Issues & Solutions

**Inverted normals after export:**
```python
code = """
import bpy
obj = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')
"""
blender:execute_blender_code(code)
```

**Scale issues in engine:** set metric/cm before export, apply all transforms, use scale=1.0.

**Texture not showing:** embed textures in FBX, keep UVs in 0–1, verify engine material setup.

**Animation artifacts:** disable "Add Leaf Bones", avoid "All Actions", keep consistent bone orientation (Primary X, Secondary -Z).

**Faceted low-poly look:** you skipped bevels — run `bevel_all_sharp()` and enable auto-smooth.

**Model looks "generated" / off:** you skipped the critique loop — render multiple views and fix against the checklist.
