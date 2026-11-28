# Code map: Materials and texturing

materials, procedural presets, PBR, node graphs, masks, wear, baking, UVs, texel density. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/blendworks_bridge/ (23)

- `bake_sizes`: Per-material and per-channel bake image size rules and the GPU memory they imply. | fn: gpu_bytes size_rules_schema + | test: bake_sizes
- `baking`: Bake machinery: scene settings, emission swaps and the Blender bake operator run. | fn: SceneSettings shading_materials + | test: bake bake_failures +1
- `brass`: Brass material schema and the ageing of brass surfaces. | fn: brass_schema aged + | test: brass brass_ageing
- `graph_build`: Builds a node graph from a description: sockets, settings and input values. | fn: socket_names find_socket + | test: material_nodes
- `graph_catalog`: Catalog of the allowed shader node kinds. | fn: NodeKind | test: material_nodes
- `graph_read`: Reads a node graph back into the description format, listing only changed settings and inputs. | fn: plain socket_value + | test: material_nodes
- `marble`: Marble material: finish and vein layers with capillaries and clouds. | fn: finish_schema veins_schema + | test: marble marble_finish
- `masks`: Geometric masks for procedural materials (window, axis and height masks). | fn: geometric_schema mask_kinds + | test: brass procedural +1
- `materials_info`: Reads a material's Principled node and summarises it. | fn: principled_node material_summary | test: materials pbr
- `natural`: Shared helpers of the natural material presets: scaling, tones and vectors. | fn: amount scaled + | test: natural_materials
- `nodes`: Shader node graph helper with socket lookup. | fn: find_socket Graph | test: materials pbr
- `occlusion`: Ambient occlusion mask for procedural materials. | fn: occlusion_mask | test: brass procedural +1
- `pbr`: PBR material builder: colour spaces, maps, warnings and glTF group. | fn: required_colorspace assign_colorspaces + | test: pbr textured_prop
- `presets`: Procedural material presets (wood, worn metal, rust, stone). | fn: scaled spread + | test: brass marble_finish +2
- `procedural`: Procedural material builder: preset definitions, seeds and the surface Principled node. | fn: Preset common_properties + | test: procedural
- `scratches`: Scratch direction schemas and mapping of scratch axes onto a surface. | fn: scratch_axis_schema is_around + | test: brass procedural +1
- `texel`: Texel density: UV and world areas and scaling UVs to a density. | fn: uv_area world_area + | test: uv_texel
- `uv_coverage`: UV coverage packing: merging islands and searching a layout for a coverage target. | fn: merge_islands Layout + | test: uv_coverage
- `uv_islands`: UV island graphs: edge axes, overlap and similarity. | fn: edge_axes separated + | test: uv_coverage uv_texel
- `uv_project`: UV projection onto nearest faces. | fn: read single + | test: uv_coverage uv_texel
- `uvlayout`: UV island layout: shelves and best layout packing. | fn: island_boxes shelves + | test: lathe loft +3
- `wear`: Wear maths: jitter, dents and site picking. | fn: vertex_key unit_ball + | test: wear
- `wire_edges`: Wire edge node group builder. | fn: Builder corner_offset + | test: render_views

### bridge/blendworks_bridge/commands/ (8)

- `bake`: The bake command: bakes material channels into images, optionally from high-poly sources, and rewires the material. | fn: samples_schema plan_bake + | cmd: bake | test: bake bake_failures +1
- `material_nodes`: The material_nodes and material_info commands: build and read a material as a node graph. | fn: input_schema setting_schema + | cmd: material_nodes material_info | test: material_nodes
- `materials`: Material commands: add_material, assign_material and vertex_colors. | cmd: add_material assign_material vertex_colors | test: materials pbr
- `pbr`: The material_pbr command: a Principled material built from PBR image maps. | fn: map_properties plan_material_pbr + | cmd: material_pbr | test: pbr textured_prop
- `procedural`: The material_procedural and material_layer commands: procedural presets and masked layers. | fn: ensure_material preset_properties + | cmd: material_procedural material_layer | test: procedural
- `uv`: UV commands: uv_smart_project, uv_unwrap and uv_info. | fn: uv_mesh_object run_in_edit_mode + | cmd: uv_smart_project uv_unwrap uv_info | test: uv_texel
- `uv_pack`: The uv_pack command: packs the UV islands of several meshes into one atlas. | fn: object_group summary + | cmd: uv_pack | test: uv_texel
- `wear`: The displace_noise command: seeded, bounded wear (jitter and dents) on a mesh. | fn: vertex_weights allowed_vertices | cmd: displace_noise | test: wear
