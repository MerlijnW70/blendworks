# Code map: Terrain, rock and liquids

heightfields, erosion, noise, land and distant land, liquid_*, stones, fracture, chip, abrade. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/blendworks_bridge/ (47)

- `abrasion`: Abrasion maths: refines a mesh and splits its faces into a worn, rounded pattern. | fn: mesh_triangles edge_table + | test: rocks-example
- `erosion_droplets`: Hydraulic erosion by simulated water droplets on a height grid. | fn: locate height_and_gradient + | test: erode eroded-terrain-example
- `erosion_thermal`: Thermal erosion: material slides downhill past the talus angle. | fn: neighbour_slices distances + | test: eroded-terrain-example
- `fracturing`: Fracture maths: random directions and cuts of a convex solid into pieces. | fn: random_direction binary_pieces + | test: rocks-example
- `fragments`: Fragments of a fractured or chipped solid: materials, slots and the solid read from an object. | fn: fresh_material plan_fresh_material + | test: rocks-example
- `heightgrid`: Height grid tiles and tile sets for terrain. | fn: grid_resolution Tile + | test: eroded-terrain-example
- `land_border`: How distant land meets the region: at each border point the land takes the region's height and outward slope, and the | fn: fade smooth_periodic + | test: landscape_air
- `land_field`: The height field of distant land: octaves of gradient noise whose amplitudes are calibrated until the land measures as | fn: noise_moments smoothstep + | test: landscape_air
- `land_material`: The ground material of distant land: a copy of the region's own material, so the ground continues at the border with | fn: principled_of attribute + | test: landscape_air
- `land_region`: What distant land needs to know about the region it surrounds: its rectangle, its heights on a grid and along its | fn: evaluated_triangles Surface + | test: landscape_air
- `land_rings`: The ring mesh of distant land: closed rectangular loops around the region at growing offsets, joined loop to loop by | fn: Rect ring_loops + | test: landscape_air
- `land_stats`: Statistics of a height grid that describe the character of land: relief, slopes, the variance in each octave band of | fn: plane_residual band_wavelengths + | test: distant_land
- `liquid_bodies`: Liquid bodies: basins, fetch, levels and local bottoms. | fn: default_cell fetch_along + | test: liquid_bodies
- `liquid_cavity`: The cavity of a container that liquid fills, as voxels and inner faces. | fn: container_arrays welded + | test: liquid_bodies liquid_fill +3
- `liquid_container`: Container walls for liquid fills: tilt, wall offsets and boundary loops. | fn: tilt_matrix vertex_offsets + | test: liquid_bodies liquid_fill +3
- `liquid_extras`: Extra liquid forms: puddles, edge profiles and spill rings. | fn: outline polygon_area + | test: liquid_bodies liquid_fill +3
- `liquid_foam`: Foam and bubble materials for liquid surfaces. | fn: boundary_edges head + | test: liquid_bodies liquid_fill +3
- `liquid_grid`: Flood fill of liquid over a ground grid. | fn: world_triangles Ground + | test: liquid_bodies
- `liquid_light`: Photometry for liquids: blackbody, emission strength and diffuse reflectance. | fn: photopic planck + | test: liquid_scene
- `liquid_masks`: Depth and band masks of liquid bodies. | fn: corner_depth band + | test: liquid_bodies liquid_fill +3
- `liquid_mesh`: Liquid surface meshes: building, volume, area and closing sheets. | fn: build_mesh flag + | test: liquid_fill
- `liquid_ocean`: Ocean surface grid, skirt and beach heights. | fn: square_grid skirt + | test: liquid_bodies liquid_fill +3
- `liquid_presets`: Liquid presets: water, sediment, honey and their optical properties. | fn: sediment water + | test: honey_classes liquid_fill +1
- `liquid_render`: Render settings for liquid scenes. | fn: configure | test: liquid_scene
- `liquid_ripples`: Ripple detail tiles and slope statistics for liquid surfaces. | fn: mesh_cutoff detail_tile + | test: liquid_bodies liquid_fill +3
- `liquid_river`: River paths: smoothing, a running minimum bed profile and carving. | fn: Path chaikin + | test: liquid_bodies
- `liquid_shader`: Shader graph builder for liquid materials. | fn: LiquidGraph fresh_material + | test: liquid_optics
- `liquid_spectrum`: Sea state: wave spectrum, wavelengths, whitecaps and slope variance. | fn: sea_state peak_wavelength + | test: liquid_bodies
- `liquid_world`: Liquid objects in the scene, wind and storm state. | fn: piecewise storm_of + | test: liquid_bodies liquid_scene +2
- `noise`: Seeded noise functions: lattice hash, Perlin and feature points. | fn: finalize lattice_hash + | test: noise_displace noise_math +1
- `noise_stack`: Noise stacks: octaves, gains and domain warping evaluated in world metres. | fn: octave_frame octave_point + | test: heightfield noise_displace +2
- `polyhedron`: Convex solid data structure with box UVs, face splits and compaction. | fn: Solid box_uv + | test: chip fracture
- `stone_plan`: Stone placement plan: size bands, spacing and matrices. | fn: clark_evans normal_cdf + | test: shore_stones
- `stone_shape`: Stone shapes: hull, resampling and roundness. | fn: mesh_arrays volume + | test: shore_stones
- `terrain`: Terrain tile mesh: grid points, heights, rim and unfold. | fn: grid_points surface_heights + | test: terrain_kernels terrain_loader +5
- `terrain_bundle`: Selects the prebuilt native terrain core for the running platform and checks its sha256 against the release manifest. | fn: platform_key bundled_roots + | test: native_dist
- `terrain_core`: Loader of the native terrain core: finds and loads the library through ctypes, describes numpy buffers, falls back with one stated reason. | fn: NativeError CoreMissing + | test: native_dist terrain_loader +1
- `terrain_diffusion`: Python reference of hillslope diffusion: linear by ADI and non-linear critical-slope diffusion (Roering et al. 1999). | fn: check_settings cross_gradient + | test: terrain_kernels terrain_loader +4
- `terrain_flood`: Python reference of Priority-Flood with epsilon (Barnes et al. 2014). | fn: ordered_key next_up + | test: terrain_kernels terrain_loader +4
- `terrain_flow`: Python reference of flow receivers: D8 and multiple flow with exponent p, flats resolved (Barnes 2014). | fn: neighbour_heights steepest + | test: terrain_kernels terrain_loader +4
- `terrain_grid`: Grid description shared by the terrain kernels: shape, spacing, outlet edges and cell status. | fn: TerrainGrid flat_heights | test: terrain_loader terrain_physics +1
- `terrain_incision`: Python reference of implicit stream-power incision (Braun & Willett 2013), closed form for n = 1 and Newton for general n. | fn: check_law solve + | test: terrain_kernels terrain_loader +4
- `terrain_kernels`: Dispatch of the terrain kernels to the native core or the Python references. | fn: default_threads chosen_core + | test: terrain_kernels terrain_loader +3
- `terrain_lakes`: Python reference of lake routing by the basin graph and its minimum spanning tree (Cordonnier, Bovy & Braun 2019). | fn: Lakes ordered_bits + | test: terrain_kernels terrain_loader +4
- `terrain_order`: Python reference of the breadth-first receiver queue with levels (Barnes 2019) and accumulation along it. | fn: Ordering check_table + | test: terrain_kernels terrain_loader +4
- `terrain_pow`: Portable exp, ln and pow from basic arithmetic, so both engines give the same bits on every platform. | fn: atanh_coefficients exp_coefficients + | test: terrain_kernels terrain_loader +4
- `terrain_thermal`: Python reference of thermal slides: slope-limited mass transfer with a critical angle per cell. | fn: check_settings slide | test: terrain_kernels terrain_loader +4

### bridge/blendworks_bridge/commands/ (12)

- `abrade`: The abrade command: wears the edges and corners of a closed mesh into a rounded, worn form. | fn: require_closed write_back | cmd: abrade | test: abrade rocks-example
- `blob`: The blob command: a smooth union of spheres built as metaballs and voxel remeshed into one closed mesh. | fn: stiffness_for refuse_oversize + | cmd: blob | test: remesh_blob rocks-example
- `chip`: The chip command: knocks chips off the edges and corners of a closed convex solid. | cmd: chip | test: chip rocks-example
- `distant_land`: The distant_land command: land that surrounds a region out to tens of kilometres and continues its terrain. | fn: plan_distant_land measured_region + | cmd: distant_land | test: distant_land
- `erode`: The erode command: thermal and hydraulic erosion of heightfield terrain in metres. | fn: tile_objects hydraulic_settings + | cmd: erode | test: erode eroded-terrain-example
- `fracture`: The fracture command: breaks a closed convex solid into closed convex pieces. | fn: piece_name make_piece + | cmd: fracture | test: fracture rocks-example
- `heightfield`: The heightfield command: a terrain tile from the noise stack at world coordinates. | fn: positive_pair tile_inside_world | cmd: heightfield | test: heightfield eroded-terrain-example
- `liquid_body`: The liquid_body command: ocean, lake, river and beach water at world scale. | fn: plan_liquid_body sample_depth + | cmd: liquid_body | test: liquid_bodies liquid_fill +3
- `liquid_fill`: The liquid_fill command: fills a container with a liquid, with a meniscus and glass interface. | fn: plan_liquid_fill free_material_name + | cmd: liquid_fill | test: liquid_fill
- `material_liquid`: The material_liquid command: physically based liquid material for water and other liquids. | fn: resolved describe_entry + | cmd: material_liquid | test: material_nodes materials
- `noise_displace`: The noise_displace command: displaces a mesh with a seeded noise stack in metres. | fn: allowed_mask weight_array + | cmd: noise_displace | test: noise_displace noise-terrain-example
- `shore_stones`: The shore_stones command: stones clustered along a water line. | fn: pair plan_shore_stones + | cmd: shore_stones | test: shore_stones
