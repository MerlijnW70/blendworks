# Code map: Judge

src/judge and bridge/judge: spec, rules, measurement stages, visual judge, container entry. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/judge/ (41)

- `gpu_warm`: Warms the GPU kernel cache with a small scene before judging. | fn: warm_scene warm + | test: judge/
- `judge`: Entry point of the judge's Blender process: runs the measurement stages on an asset. | fn: main | test: judge/
- `judge_albedo`: Measures base colour images through triangle UVs by rasterizing them. | fn: base_colour_images triangle_materials + | test: judge/
- `judge_armature`: Measures armatures: bone depths and rig data. | fn: armatures_in bone_depths + | test: judge/
- `judge_bind`: Reads inverse bind matrices and node transforms of skins. | fn: BindUnreadable numbers + | test: judge/
- `judge_budget`: Predicts mesh size after modifiers to enforce budgets. | fn: Unbounded Shape + | test: judge/
- `judge_closeup`: Close-up renders and their composition into a sheet. | fn: world_points Framing + | test: judge/
- `judge_colours`: Collects colours of an asset. | fn: ColourCollector | test: judge/
- `judge_common`: Shared judge helpers: errors, quoting and argument splitting. | fn: JudgeError FileLockError + | test: judge/
- `judge_device`: Render device selection for the judge. | fn: cycles_preferences backend_devices + | test: judge/
- `judge_finite`: Checks that meshes, curves and objects hold only finite numbers. | fn: all_finite matrix_finite + | test: judge/
- `judge_font`: Bitmap font text drawing for judge sheets. | fn: printable text_width + | test: judge/
- `judge_geometry`: Geometry read helpers: world coordinates, faces and triangle areas. | fn: top_ancestor world_coordinates + | test: judge/
- `judge_gltf`: Reads glTF files directly: accessors, triangles and instances. | fn: entries whole + | test: judge/
- `judge_images`: Reads image dimensions from BMP, TGA, TIFF, EXR and HDR headers. | fn: bmp_size tga_size + | test: judge/
- `judge_instances`: Instance detection: name patterns, welded parts and frames. | fn: name_pattern vertex_labels + | test: judge/
- `judge_load`: Loads an asset into a clean scene from glTF, FBX, OBJ or blend. | fn: detect_format empty_scene + | test: judge/
- `judge_measure_stage`: The measure stage: object tolerances, extras and measurement. | fn: floating_tolerance objects_wanted + | test: judge/
- `judge_motion`: Motion measurement: animation blocks, held poses and clip curves. | fn: scene_fps animated_blocks + | test: judge/
- `judge_natural`: Natural asset measurements: vertex samples and deviation angles. | fn: natural_parts size_option + | test: judge/
- `judge_objects`: The object table of the scene being judged. | fn: ObjectTable | test: judge/
- `judge_opacity`: Reads opacity from materials. | fn: source value_source + | test: judge/
- `judge_outlines`: Outline graphs for silhouettes. | fn: OutlineGraph add_outlines | test: judge/
- `judge_parity`: Parity checks between the original and the loaded asset (modifiers, particles, curves). | fn: match_modifiers match_particles + | test: judge/
- `judge_parts`: Connected components and overlaps of an asset's parts. | fn: components overlaps + | test: judge/
- `judge_pass`: The judge passes: chooses stages, runs each and digests the files. | fn: chosen_stages Progress + | test: judge/
- `judge_paths`: Checks of references and paths inside asset files. | fn: code_units decode_uri + | test: judge/
- `judge_rays`: Portable random rotations and sine and cosine for ray casting. | fn: reduced series_sin + | test: judge/
- `judge_render_stages`: Render stages: views, silhouettes and cutouts. | fn: chosen_views silhouette_views + | test: judge/
- `judge_rig`: The judge's studio rig: scene, world and orientation. | fn: basis orientation + | test: judge/
- `judge_sheet`: Composes contact sheets from images, UV tiles and text. | fn: Canvas load_png + | test: judge/
- `judge_shells`: Mesh shell analysis: disjoint sets, edge defects and volume. | fn: DisjointSet empty_topology + | test: judge/
- `judge_skeleton`: Skeleton digest and radii measurement for tree assets. | fn: unit plane_basis + | test: judge/
- `judge_skeleton_checks`: Skeleton checks: edge samples and branching. | fn: EdgeSamples evenly + | test: judge/
- `judge_skeleton_read`: Parses a skeleton from an asset. | fn: SkeletonError plain + | test: judge/
- `judge_skin`: Skin measurement: rigs, weights and rest pose. | fn: skinning_rigs face_vertices + | test: judge/
- `judge_stage_scene`: Stages the scene for a measurement and removes what was created. | fn: data_pointers remove_created + | test: judge/
- `judge_surface`: Surface ray casting for the judge. | fn: triangle_area triangle_normal + | test: judge/
- `judge_textures`: Texture measurement: colour spaces, mip chains and GPU bytes. | fn: expected_space mip_chain_pixels + | test: judge/
- `judge_uv`: UV measurement: areas, outside the unit square and grids. | fn: uv_area outside_unit_square + | test: judge/
- `low_integrity`: Starts the judge's Blender at low integrity on Windows through the process API. | fn: SidAndAttributes MandatoryLabel + | test: judge/

### src/judge/ (53)

- `bin.js`: Executable entry of the judge CLI.
- `blend-refs.ts`: Scans a .blend file for the files it references.
- `cli.ts`: The judge command line: judge, diff, closeups, visual eval and silhouettes.
- `closeups.ts`: Renders close-up views of an asset into a sheet.
- `delivery.ts`: Reads and checks a delivered folder of files.
- `device.ts`: Render device modes and GPU backend probing.
- `diff.ts`: Reads two judge reports and lists what changed.
- `fbx.ts`: Reads texture references from FBX files.
- `fft.ts`: Fast Fourier transform and circular autocorrelation.
- `gpu-cache.ts`: Warms the GPU kernels.
- `infrastructure.ts`: Tells infrastructure failures from asset failures.
- `integrity-rules.ts`: Rules for manifold meshes, surfaces and self-contained files.
- `isolation.ts`: Marks the container isolation and infrastructure exit codes.
- `judge-pass.ts`: Plans the one-pass judge run and reads what it measured.
- `kernel-cache.ts`: Cache of compiled render kernels.
- `measurements.ts`: Schemas of what the Blender stages measure.
- `motion-measurements.ts`: Schemas of motion measurements (bones, rigs, rest poses).
- `motion-rules.ts`: Rules for rigs, bones and clips.
- `motion-spec.ts`: The motion part of the asset spec and its limits.
- `motion-summary.ts`: Summary lines of the motion measurements.
- `natural-checks.ts`: Check helpers for natural asset ranges and sets.
- `natural-cited.ts`: Cited limits of natural assets.
- `natural-defaults.ts`: Calibrated defaults of the natural asset rules.
- `natural-leonardo.ts`: Solves the Leonardo branching exponent.
- `natural-measures.ts`: Box counting and edge measures of natural assets.
- `natural-power.ts`: Power law fits for size distributions.
- `natural-repetition.ts`: Detects texture and instance repetition.
- `natural-schema.ts`: Schemas of the natural asset measurements.
- `natural-sets.ts`: Set-level natural checks: size distribution, Leonardo and repetition.
- `natural-spec.ts`: The natural part of the asset spec: classes, rules and limit names.
- `natural.ts`: Natural asset stage: silhouettes, dimensions and solidity views.
- `object-rules.ts`: Per-object rules with glob patterns.
- `onepass.ts`: Stage groups of the single Blender pass.
- `path-policy.ts`: Policy for references and paths inside asset files.
- `reference-spec.ts`: The reference silhouette part of the asset spec.
- `reference.ts`: Loads reference silhouettes and compares them.
- `render-profile.ts`: Render profile of the judge and of tests.
- `render-stage.ts`: The render stage: resolution, samples and budget.
- `report.ts`: Types of the judge report.
- `rules.ts`: Evaluates the rules of a spec against measurements.
- `run.ts`: The judge entry function: runs the stages and builds the report.
- `sandbox.ts`: Sandbox flags and scripts for running Blender on untrusted assets.
- `shape-rules.ts`: Shape rules: origin, placement, scale and axes.
- `shared-access.ts`: Shared access to a file with a time limit.
- `silhouette.ts`: Silhouette masks and their comparison.
- `silhouettes.ts`: The silhouettes command: renders silhouettes of an asset.
- `spec-shapes.ts`: Shared shapes of the spec schema.
- `spec.ts`: The asset spec schema and its defaults.
- `stages.ts`: Runs the judge's Blender stage scripts.
- `texture-rules.ts`: Texture, validator and parts rules.
- `untrusted.ts`: Neutralises untrusted text before it goes into a report.
- `validator.ts`: Runs the Khronos glTF validator.
- `version.ts`: Checks the Blender version.

### src/judge/container/ (7)

- `asset.ts`: Judges one asset inside the judge container.
- `cpus.ts`: CPU quota and the number of jobs inside the container.
- `entry.ts`: Entry point of the container: asset or patch mode.
- `inputs.ts`: Locates the inputs mounted into the container.
- `patch.ts`: Applies a patch in the container and runs the full check.
- `probe.ts`: Probes the container host.
- `result.ts`: The result line, exit codes and errors of the container entry.

### src/judge/visual/ (14)

- `anthropic.ts`: The Anthropic API provider of the visual judge.
- `claude-code.ts`: The Claude Code provider of the visual judge.
- `eval.ts`: Evaluates the visual judge on labelled sets.
- `images.ts`: Prepares the evidence images of the visual judge.
- `judge-stage.ts`: The visual stage of the judge run.
- `png.ts`: A small PNG decoder.
- `prices.ts`: Model prices and usage accounting.
- `process.ts`: Spawns the Claude process with output limits.
- `prompt.ts`: The visual judge prompt and answer schema.
- `provider.ts`: Provider selection and request settings for the visual judge.
- `record.ts`: The visual record and its status.
- `score.ts`: Combines sample scores: median, majority and quorum.
- `spec.ts`: The visual part of the asset spec and its defaults.
- `stage.ts`: Scores an asset visually with a committee of samples.
