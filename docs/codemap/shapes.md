# Code map: Shapes and modelling

sweep, lathe, loft, solids, shells, mesh edits, modifiers, objects, transforms, placement, scatter, engraving, text, cleaning, LODs. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/blendworks_bridge/ (43)

- `analytic_paths`: Exact circle, arc and helix paths for sweeps, with segment counts from a chord tolerance. | fn: path_fields unit_axis + | test: lathe loft +3
- `builder`: Shared finishing step for shape builders. | fn: finish_shape | test: lathe loft +3
- `chain`: Geometry of roller chain parts: plates, rollers, pins and the wheel path. | fn: ChainSizes stadium + | test: outline_solids roller_chain
- `cleaning`: Mesh cleaning maths: sliver triangles, altitudes and collinear vertex removal. | fn: triangle_table triangle_altitudes + | test: clean_mesh
- `copies`: Linked and realized copies of objects with unique child names. | fn: child_name require_free_names + | test: instances scatter +1
- `cutmarks`: Marks the edges of a cut so later steps can find the engraved or booleaned faces. | fn: mark_cutter unmark + | test: clean_mesh engrave +1
- `cutters`: Cutter geometry for booleans: folded loops, crossings and triangulation. | fn: crossing folded_loop + | test: early_counts engrave_cutters
- `edge_order`: Canonical order of mesh edges so results do not depend on Blender's edge numbering. | fn: read write + | test: edge_order
- `engraving`: Engraving engine: samples the surface, chooses a solver and applies the cutter. | fn: UvSampler sampler_for + | test: engrave engrave_overlap +1
- `extrusion`: Extrusion maths for outlines: loops, insets, caps and level tables. | fn: level_table inset_loops + | test: outline_solids roller_chain
- `flatfill`: Flat polygon fill: dissolving flat faces and constrained Delaunay filling. | fn: area_vector dissolve_flat + | test: clean_mesh engrave +1
- `gears`: Gear and sprocket outlines: involute flanks, tooth angles and seats. | fn: involute polar + | test: outline_solids roller_chain
- `glyph_data`: Data table of symbol outlines used by engraving. | test: engrave
- `glyphs`: Glyph outlines from fonts and symbols: Bezier flattening and curve loops. | fn: symbol_names symbol_loops + | test: engrave
- `instancing`: Placement frames for instances along paths, edge chains, circles and points. | fn: frame_matrix normal_matrix + | test: instances scatter +1
- `lofting`: Loft maths: section matching, travel direction and ring skinning. | fn: raise_count section_matrix + | test: lathe loft +3
- `mesh_attributes`: Mesh attributes in world space: normals, slopes, curvature and surface corners. | fn: world_arrays polygon_vertex_index + | test: mesh_data mesh_edit
- `modifier_growth`: Lower bounds on the vertex counts of the modifiers that multiply a mesh, known before Blender evaluates them. | fn: InputShape input_shape + | test: early_counts
- `modifier_specs`: Field specs and unit conversion for modifier settings. | fn: Field upper + | test: modifier_kit modifiers
- `normals`: Hardened loop normals for sharp edges. | fn: hardened_loop_normals | test: mesh_edit selection_kit
- `outlines`: 2D outline helpers: winding, repeated points, circle points and offset loops. | fn: signed_area counter_clockwise + | test: engrave
- `paths`: 3D path helpers: cleaning, lengths, turn angles and corner fillets. | fn: vectors clean_path + | test: lathe loft +3
- `phyllotaxis`: Phyllotaxis layout on a disc: sites, divergence and age curves. | fn: Site Layout + | test: phyllotaxis phyllotaxis-example
- `phyllotaxis_surface`: Phyllotaxis on cylinders, cones, spheres and surfaces of revolution. | fn: uniform_scale rigid_world + | test: phyllotaxis phyllotaxis-example
- `poisson`: Poisson disc spacing: disk grid, overlap tests and thinning. | fn: DiskGrid overlaps + | test: instances scatter +1
- `profiles`: Profile schemas and presets (circle, rectangle) for sweeps. | fn: profile_fields rounded_rectangle + | test: shell_surface
- `revolve`: Lathe maths: profile cleaning, axis splitting, rings and caps. | fn: clean_profile split_axis + | test: lathe loft +3
- `scatter_frames`: Scatter instance frames: axes, tilt and instance matrices. | fn: axis_directions reference_frame + | test: scatter scatter_options +1
- `scatter_masks`: Scatter masks: slope, height and ramp masks over a surface. | fn: chosen_masks inside + | test: scatter scatter_options +1
- `scatter_plan`: Scatter planning: dart count, size checks and the resulting plan. | fn: ScatterPlan mean_square_size + | test: scatter scatter_options +1
- `scatter_sizes`: Scatter size distributions: power law, lognormal and histograms. | fn: power_sizes lognormal_sizes + | test: scatter scatter_options +1
- `scatter_surface`: The surface scatter reads: triangles, corner normals and weights. | fn: Surface corner_normals + | test: scatter scatter_options +1
- `shading`: Smooth and flat shading with hard corners. | fn: hard_corners apply_shading | test: lathe loft +3
- `shell`: Shell builder: spiral rings, hardening and shell mesh data. | fn: build_spiral harden_ring + | test: shell shell_surface +2
- `shell_profile`: Shell generating curve profiles. | fn: smoothstep Profile + | test: shell shell_surface +2
- `shell_rings`: Shell spiral rings. | fn: Spiral | test: shell shell_surface +2
- `shell_wall`: Shell wall thickness: probes, measured walls and cavity start. | fn: vertex_normals surface_tree + | test: shell_wall shells-example
- `skin`: Skinning of ring sections into a surface with caps and planar UVs. | fn: ring_distances mean_gap + | test: lathe loft +3
- `slivers`: Sliver detection: triangle shapes, UV aspects and link conditions. | fn: Limits loop_triangles + | test: clean_mesh engrave +1
- `surfaces`: Engraving surfaces: plane, face region, cylinder, ring and path. | fn: default_up plane_frame + | test: early_counts engrave_cutters
- `sweeping`: Sweep maths: rotation-minimising frames, miters and rings along a path. | fn: initial_normal orthogonal + | test: sweep
- `textlayout`: Text layout: splitting runs and placing glyph loops. | fn: split_runs run_loops + | test: engrave engrave_cutters
- `topology`: Mesh topology reports: manifold check, Euler characteristic and problems. | fn: manifold_report euler_characteristic + | test: clean_mesh tree_mesh

### bridge/blendworks_bridge/commands/ (18)

- `clean`: The clean_mesh command: repairs a mesh after booleans (welds, degenerate faces, slivers, normals). | fn: clean_object | cmd: clean_mesh | test: clean_mesh
- `engrave`: The engrave command: cuts or embosses text and symbols along a plane, cylinder, ring or curve. | fn: surface_properties ring_schema + | cmd: engrave | test: engrave engrave_cutters +3
- `geometry`: Commands that build geometry from data: mesh_from_data, curve_from_points and text_object. | fn: with_placement read_data_file + | cmd: mesh_from_data curve_from_points text_object | test: geometry
- `hierarchy`: Scene structure commands: add_empty and collection create, link and unlink. | fn: scene_collections get_collection + | cmd: add_empty collection_create collection_link collection_unlink | test: hierarchy
- `lods`: The generate_lods command: LOD copies of a mesh by decimation that keeps UVs and borders. | fn: core rounded_level + | cmd: generate_lods | test: lods package_math
- `mesh_edit`: Mesh edit commands: extrude, inset, bevel, subdivide, shading, normals and merge by distance. | fn: with_faces world_scale + | cmd: extrude inset bevel subdivide shade_smooth shade_flat recalc_normals merge_by_distance | test: mesh_edit
- `mesh_query`: The mesh_query and transform_selection commands: find faces and move the selected faces. | fn: selection_fields material_name + | cmd: mesh_query transform_selection | test: mesh_edit selection_kit
- `modifiers`: Modifier commands: add_modifier, apply_modifier, boolean, mirror, array, solidify and decimate. | fn: finish_modifier evaluated_counts + | cmd: apply_modifier boolean mirror array solidify decimate add_modifier | test: modifiers
- `objects`: Object commands: add_primitive, duplicate, join, rename and parent. | fn: unique_name plan_add_primitive + | cmd: add_primitive duplicate join rename parent | test: objects
- `placement`: Placement commands: instances (linked copies along points, paths and circles) and rivet_line. | fn: age_curve placements_from + | cmd: instances rivet_line | test: phyllotaxis
- `remesh`: The remesh command: rebuilds a mesh as one clean surface of even voxels. | fn: surface_area shell_count + | cmd: remesh | test: remesh_blob rocks-example
- `roller_chain`: The roller_chain command: a roller chain with alternating inner and outer links. | cmd: roller_chain | test: roller_chain early_counts
- `scales`: The engrave_scale command: the tick marks of a dial cut or embossed in one boolean. | fn: class_schema scale_surface + | cmd: engrave_scale | test: scales early_counts
- `scatter`: The scatter command: copies of meshes over a surface with Poisson-disc spacing. | fn: range_pair sources_from + | cmd: scatter | test: scatter scatter_options +1
- `shapes`: Shape commands: lathe, sweep and loft build meshes from profiles and paths. | fn: with_shape_fields sweep_path + | cmd: lathe sweep loft | test: lathe loft +3
- `shell`: The shell command: a closed Raup shell grown from a generating curve along a spiral. | cmd: shell | test: shell shell_surface +2
- `solids`: Solid commands: extrude_outline, gear and sprocket. | fn: shape_fields bore_loop + | cmd: extrude_outline gear sprocket | test: outline_solids roller_chain
- `transforms`: Transform commands: transform, apply_transform and set_origin. | fn: editable_data_object bake | cmd: transform apply_transform set_origin | test: objects
