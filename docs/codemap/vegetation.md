# Code map: Vegetation and ground cover

tree_*, trees, meadow_*, lsystem*, cover_*, ground_cover, forest_*, distant_forest, impostors. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/blendworks_bridge/ (55)

- `cover_blades`: Grass blade geometry for ground cover: triangles, widths, shapes and clumps. | fn: blade_triangles blade_plan + | test: cover_budget cover_contact +3
- `cover_contact`: Ground contact shading for ground cover: triangle coverage and contact values. | fn: triangle_coverage vertex_values + | test: cover_contact
- `cover_flowers`: Flower geometry for ground cover: stems, heads, petals and centres. | fn: flower_frame stem_points + | test: cover_budget cover_contact +3
- `cover_gltf`: Reads and writes .glb files and adds GPU instancing for ground cover export. | fn: read_glb padded + | test: cover_budget cover_contact +3
- `cover_kinds`: Ground cover element kinds: parameters, budgets, geometry and materials. | fn: pair element_params + | test: cover_review
- `cover_litter`: Litter geometry for ground cover: twigs, leaf cards and tubes. | fn: twig_axes axis_nodes + | test: cover_budget cover_contact +3
- `cover_masks`: Ground cover masks: obstacles, distance, noise and view masks per population. | fn: soft_band Obstacles + | test: cover_masks
- `cover_materials`: Ground cover shader helpers: per-instance randomness, UV parts and blade grass. | fn: amount instance_random + | test: cover_budget cover_contact +3
- `cover_mesh`: The mesh of one ground cover element and its rotation and segment helpers. | fn: ElementMesh rotate_about + | test: cover_budget cover_contact +3
- `cover_nodes`: Geometry node group that builds ground cover instances. | fn: named switch + | test: cover_budget cover_contact +3
- `cover_plan`: Ground cover planning: drawing candidates, budgets and populations of placed instances. | fn: Draw candidate_limit + | test: cover_budget cover_contact +3
- `cover_populations`: Ground cover populations: merging presets with the caller's kind groups. | fn: pair kind_group + | test: cover_budget cover_contact +3
- `cover_presets`: Data table of ground cover presets. | test: cover_budget cover_contact +3
- `cover_sampling`: Ground cover sampling: view, candidate points, usable areas and barycentric draws. | fn: View Candidates + | test: cover_budget cover_contact +3
- `cover_shading`: Ground cover shading: preset materials, instance tint and ground darkening. | fn: preset_material instance_tint + | test: cover_budget cover_contact +3
- `forest_canopy`: The canopy surface of distant forest: past the cards the land itself rises by the canopy height times the forest | fn: canopy_surface crown_colour | test: distant_forest
- `forest_cards`: Impostor cards, their material, the canopy surface far out, and the calibration that makes a card as bright as the tree | fn: card_mesh blended + | test: distant_forest
- `forest_grove`: Calibration of impostor brightness in a grove: a small stand of trees on a ground, seen from the camera's direction | fn: Grove compare | test: distant_forest
- `forest_inplace`: Calibration of impostor brightness in the scene itself. The trees nearest beyond the switch are rendered from the | fn: render InScene + | test: distant_forest
- `forest_place`: Where distant forest grows, and how each tree is drawn. The land's vertices get a forest share from rules (slope, | fn: vertex_areas patch_noise + | test: distant_forest
- `ground_level`: The low ground around the camera, where ground fog lies. | fn: low_ground | test: ground_cover ground_export
- `impostors`: Octahedral impostors of trees. A tree is drawn into an atlas of frames x frames views over the upper hemisphere, laid out | fn: decode encode + | test: distant_forest
- `lsystem_derive`: L-system derivation: rule tables, arithmetic checks and rule application. | fn: Derivation RuleTable + | test: lsystem_grammar lsystem_turtle +1
- `lsystem_expr`: L-system expression scanner and evaluator. | fn: truth binary + | test: lsystem_grammar lsystem_turtle +1
- `lsystem_plan`: L-system planning: resolves a request into a checked word with organs. | fn: Planned resolve + | test: lsystem_grammar lsystem_turtle +1
- `lsystem_presets`: L-system presets such as a bracketed plant and Honda trees. | fn: bracketed honda + | test: lsystem_grammar lsystem-example
- `lsystem_rules`: L-system rule and axiom parsing. | fn: refuse_symbol read_modules + | test: lsystem_grammar lsystem_turtle +1
- `lsystem_turtle`: L-system turtle: state, vector helpers and organs placed along the word. | fn: cosine_sine combine + | test: lsystem_turtle lsystem-example
- `tree_axes`: Tree axes and twigs built from a skeleton. | fn: Axis Twig + | test: tree_batch tree_colonization +14
- `tree_bark`: Bark mesh: tubes skinned or voxel remeshed with density control. | fn: Built build_tubes + | test: tree_batch tree_colonization +14
- `tree_canopy`: Tree canopy: writes meshes with materials and reports leaf variation and area. | fn: write_mesh with_materials + | test: tree_batch tree_colonization +14
- `tree_colonize`: Space colonisation growth of a tree skeleton. | fn: Nodes Group + | test: tree_colonization tree-example
- `tree_crown`: Tree crown measurement: silhouette region, rows and coverage cells. | fn: measured_objects world_bounds + | test: tree_crown tree_crown_species +2
- `tree_foliage`: Foliage sprays along branch chains. | fn: Spray chain_frames + | test: tree_foliage tree-example
- `tree_form`: Tree form: response to wind, gnarl and per-order settings. | fn: form_active per_order + | test: tree_form tree-example
- `tree_frames`: Frames along tree branches: splines, tangents and sampling. | fn: unit padded + | test: tree_batch tree_colonization +14
- `tree_habit`: Tree habit statistics: first-order branches. | fn: first_order_branches habit_statistics | test: tree_habit tree-example
- `tree_join`: Joins tree tubes into one mesh with a skin union. | fn: Arrays write_mesh + | test: tree_batch tree_colonization +14
- `tree_leaf_shader`: Leaf shader values: variants, envelope and toothed edges. | fn: attribute leaf_values + | test: tree_batch tree_colonization +13
- `tree_leaves`: Leaves along shoot chains: placement and counts. | fn: Leaf shoot_chains + | test: tree_leaves early_counts +2
- `tree_levels`: Weber-Penn style level growth of a tree. | fn: per_level rotated + | test: tree_levels tree-example
- `tree_plan`: Tree planning: presets, defaults, envelopes and the grown result. | fn: with_preset with_defaults + | test: tree_batch tree_colonization +14
- `tree_presets`: Data table of tree presets. | fn: preset_names | test: tree_shape tree_species +1
- `tree_radii`: Branch radii by pipe model, taper and branch order. | fn: children_lists Taper + | test: tree_batch tree_colonization +14
- `tree_rings`: Tube rings for branches: strips, UVs and domes. | fn: Tube clamp_folds + | test: tree_batch tree_colonization +14
- `tree_shapes`: Crown envelopes (revolution and mesh) and rejection sampling. | fn: shape_ratio segment_distances + | test: tree_colonization tree-example
- `tree_skeleton`: Tree skeleton data: checks, chains and preview curve. | fn: Skeleton plain + | test: tree_skeleton lsystem_turtle +7
- `tree_species`: Tree species data and materials. | fn: species_of merged + | test: tree_species tree_foliage +2
- `tree_sprays`: Twig sprays: style, frames and points. | fn: SprayStyle frame_of + | test: tree_foliage tree_leaf_shapes +1
- `tree_strands`: Hanging strands of weeping trees. | fn: arc_positions coefficient_of_variation + | test: tree_strands tree-example
- `tree_surface`: Tree surface data: corners, normals, creases and overlaps. | fn: corner_vertices vertex_values + | test: tree_batch tree_colonization +14
- `tree_tubes`: Tube settings: ring counts, radii, flare and predicted triangles. | fn: Settings ring_count + | test: tree_batch tree_colonization +14
- `tree_twigs`: Twig cards for foliage. | fn: twig_cards | test: tree_batch tree_colonization +14
- `tree_vectors`: Plain vector maths used by tree code. | fn: add scaled + | test: tree_batch tree_colonization +14
- `tree_voxel`: Transfers attributes from a bark skin to a voxel remeshed bark. | fn: Source barycentric + | test: tree_batch tree_colonization +14

### bridge/blendworks_bridge/commands/ (8)

- `distant_forest`: The distant_forest command: forest on distant land from the tree species, as grown variants, cards and canopy. | fn: Placed plan_forest + | cmd: distant_forest | test: distant_forest
- `ground_cover`: The ground_element and ground_cover commands: layered grass, flowers and litter over a surface. | fn: padded ElementSet + | cmd: ground_element ground_cover | test: ground_cover
- `ground_export`: The ground_cover_export command: writes a ground cover to a .glb with GPU instancing. | fn: cover_objects instance_count + | cmd: ground_cover_export | test: ground_export cover_review
- `lsystem`: The lsystem command: grows a plant from a parametric L-system with organs. | fn: organ_placements place_organs + | cmd: lsystem | test: lsystem_grammar lsystem_turtle +1
- `tree_batch`: The grow_trees command: many trees (skeleton, mesh, leaves) built in parallel workers. | fn: tree_steps made_names + | cmd: grow_trees | test: tree_batch tree-example
- `tree_leaves`: The tree_leaves command: foliage clusters or single leaves on a tree skeleton. | fn: leaf_material twig_material + | cmd: tree_leaves | test: tree_leaves early_counts +2
- `tree_mesh`: The tree_mesh command: one closed, UV-mapped bark mesh from a tree skeleton. | fn: material_for check_args + | cmd: tree_mesh | test: tree_mesh tree-example
- `trees`: Tree skeleton commands: grow_tree (space colonisation or levels) and tree_skeleton. | fn: per_level tropism + | cmd: grow_tree tree_skeleton | test: tree-example
