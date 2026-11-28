# Code map: Scripts, bench and tests

scripts/, bench/ and the layout of test/ and bridge/tests/. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bench/autosave/ (1)

- `crash.ts`: Benchmark of autosave recovery after a crash of the headless session.

### bench/terrain-kernels/ (2)

- `run.ts`: Entry point of `npm run bench:terrain`: times the terrain kernels at 1 and 4 threads in Blender and can record the speed table.
- `table.ts`: Reads the terrain benchmark results and writes the speed table into docs/terrain-core.md between its markers.

### bench/tool-selection/ (12)

- `baseline-router.ts`: Baseline ranker the router is compared against.
- `claude.ts`: Asks a Claude model to pick tools, with usage and settings, for the tool-selection benchmark.
- `core-data.ts`: Derives the core tool set scores from the benchmark sources.
- `core.ts`: Reads and checks the generated core tool file against the benchmark.
- `docs-numbers.ts`: Writes the benchmark numbers into the design document between its markers.
- `e2e.ts`: End to end tool-selection samples through the search and call tools.
- `intents.ts`: Loads the intents (what an agent asks for) used to score routing.
- `metrics.ts`: Routing metrics: rates, rankers and tokens per byte.
- `modes.ts`: The routing modes compared: product routing, search, ranker and legacy listing.
- `run.ts`: Entry point of `npm run bench:tools`: lists the tools and scores routing.
- `server.ts`: Starts an MCP server and client for the benchmark.
- `usage.ts`: Loads recorded real tool usage for the benchmark.

### bench/trees/ (1)

- `compare.mjs`: Compares tree benchmark results.

### scripts/ (20)

- `bridge-tests.mjs`: CLI of `npm run test:bridge`: runs bridge test files inside Blender.
- `build-native.mjs`: CLI of `npm run build:native`: builds the native terrain core with cargo.
- `calibrate-natural.ts`: CLI that calibrates the natural asset limits from scans and procedural recipes.
- `check-affected.mjs`: Entry point of npm run check:affected and check:fast.
- `check-container.mjs`: CLI of the container check: runs a patch through the judge image.
- `check-stress.mjs`: CLI of `npm run check:stress`: the full check under load.
- `check-watch.mjs`: Entry point of npm run check:watch: the full check on each new main commit, in the background.
- `check.mjs`: CLI of `npm run check`: the full gate.
- `clean.mjs`: CLI of `npm run clean`: empties the cache folder.
- `codemap.mjs`: CLI that writes docs/CODEMAP.md, or with --check fails when it is stale.
- `doctor.mjs`: CLI of `npm run doctor`: reports Node, Blender, GPU, sandbox and cache.
- `durations.mjs`: CLI of `npm run durations`: saves file times to scripts/durations.json.
- `fixtures.mjs`: CLI that generates the judge fixtures.
- `judge-command.mjs`: CLI that runs the judge command the way the paying judge does.
- `judge-equivalence.mjs`: CLI that compares judge runs for equivalence.
- `judge-image.mjs`: CLI that builds the Blendworks judge image.
- `mutation-study.mjs`: Entry point of npm run study:mutation, the proof that check:affected selects every test a change can break.
- `native-dist.mjs`: CLI of `npm run native:stage`, `native:manifest` and `native:verify`: stages and checks the prebuilt native cores.
- `rules.mjs`: The rules check: file size, comments and other repository rules.
- `tools.mjs`: CLI that lists the MCP tools.

### scripts/lib/ (48)

- `affected-check.ts`: Arguments, phases and printed selection of check:affected.
- `affected.ts`: Selects the tests a change can affect: shared infrastructure, the bridge's load and call reach, the core set.
- `blender-check.ts`: Checks the Blender binary and its version.
- `bridge-runner.ts`: Runs bridge test files in Blender: listing, selection and results.
- `bridge-shared.ts`: Batching of bridge test files into shared Blender processes.
- `checks.ts`: The phases of the full and fast checks.
- `clean.ts`: Implementation of the cache clean.
- `codemap.ts`: Generator of docs/CODEMAP.md and the checks that keep it in sync.
- `container-check.ts`: Runs a patch through the judge image's check in a container.
- `dep-graph.ts`: Dependency graph of the repository: imports, named paths, bridge commands by name and fixture sets.
- `doctor.ts`: Implementation of the doctor: findings on Node, Blender and devices.
- `durations.ts`: Records and reads test file durations to schedule the heaviest first.
- `entry-cache.ts`: Cache of complete entries keyed by hashed inputs.
- `equivalence.ts`: Cases and verdict comparison for judge equivalence.
- `file-limits.ts`: Per-file time limits and heartbeat defaults of the check.
- `fixture-deps.ts`: Checks that fixture scripts declare every project file they import.
- `fixtures.ts`: Generates and caches the judge fixtures.
- `heartbeat.ts`: Heartbeats that show a slot holder is alive.
- `judge-command.ts`: Builds the judge command line and its sandbox environment.
- `judge-image.ts`: Builds the judge Docker image from a commit.
- `locks.ts`: File locks with owners, liveness and wait observers.
- `memory-meter.ts`: Samples the peak memory of processes on Linux and Windows.
- `memory.ts`: The memory gate: recorded peaks, budget and when a file may start.
- `mini-yaml.ts`: Parses the block-YAML subset the CI workflow uses, so tests can read it without a dependency.
- `mutation-study-main.ts`: Command line of the mutation study.
- `mutation-study.ts`: Runs the mutation study: mutants, the whole suite, and each failing test against the selection.
- `mutation.ts`: Breaks every function of a module once, with a guard that raises after the module has loaded.
- `native-build.ts`: Builds the native terrain core offline and decides between failing and the Python fallback.
- `native-dist.ts`: Platform table, manifest and sha256 checks, staging and release-mode checks of the prebuilt native cores.
- `natural-calibration-doc.ts`: Writes the natural calibration document.
- `natural-calibration-run.ts`: Measures calibration assets with the judge.
- `natural-calibration.ts`: Constants and scans of the natural calibration.
- `natural-sources.ts`: Downloads scans and builds procedural recipes for calibration.
- `natural-textures.ts`: Measures texture repetition for calibration.
- `pass-list.ts`: Reads the list of passed tests from the vitest and bridge stages.
- `paths.ts`: The repository root and cache folder paths.
- `pipeline.ts`: Runs the check's steps side by side with hooks and the first failure stopping the rest.
- `progress.ts`: Progress announcements and overdue files of a running check.
- `python-shape.ts`: Python module shape: function bodies, module-level code, and the functions that run while modules load.
- `run.ts`: Runs Blender or another process under a slot.
- `slot-wait.ts`: Backoff and change watching while waiting for a slot.
- `slots.ts`: The Blender slots: a lock-based pool with the memory gate.
- `stress.ts`: Options and load scripts of the stress check.
- `test-names.ts`: Naming conventions between bridge modules, examples and their tests, for the code map.
- `timings.ts`: Timing records of files, processes and waits.
- `tools.ts`: Entry of the tools listing used by `npm run bench:tools`.
- `wall-clock-lint.ts`: Finds wall-clock bounds in tests.
- `watch.ts`: Background watcher of a branch: its own clone, the full check per commit, result files and status lines.

### Tests

- `test/` (vitest, 94 files without Blender): cpu-quota judge/container-entry judge/device judge/diff judge/infrastructure judge/integrity-rules judge/judge-command judge/kernel-cache judge/motion-rules judge/natural-measures judge/natural-repetition judge/natural-rules judge/natural-sets-measures judge/natural-sets-rules judge/natural-templates-sets judge/natural-templates judge/onepass judge/reference judge/rules judge/silhouette judge/spec judge/texture-rules judge/untrusted judge/visual-anthropic judge/visual-claude-code judge/visual-eval judge/visual-math judge/visual-stage library-client library-download library-live library-mcp library-refusals library-search library-tolerant mcp-connection mcp-desktop mcp-ground-cover mcp-install mcp-liquids mcp-long-calls mcp-photography mcp-recovery-message mcp-robust mcp-routing-tiers mcp-routing mcp-stdio mcp-tools mcp-weather mcp-workspace package/equivalence package/gltfpack package/ktx2-native package/ktx2 package/memory package/native-install package/native-run package/native-select package/rules package/texture-check package/zip tooling/blender-path tooling/bridge-runner tooling/check-stream tooling/check-watch tooling/concurrency tooling/container-check tooling/doctor tooling/durations tooling/entry-cache tooling/entry-use tooling/equivalence-tolerance tooling/fair-queue tooling/fixture-binaries tooling/fixture-deps tooling/fixture-key tooling/judge-budgets tooling/lock-heartbeat tooling/machine-slots tooling/memory-gate tooling/native-core tooling/native-dist tooling/native-repro tooling/natural-calibration tooling/nested-slots tooling/overlap tooling/phases tooling/process-slots tooling/scheduling tooling/session-threads tooling/slot-busy tooling/wall-clock-lint tooling/work-clock tree-realism-docs

- `test/` (vitest, 83 files that start Blender through `useBlenderSlot()`): autosave-crash blender characters-example eroded-terrain-example export-options horizon-views-example judge/broken judge/characters judge/closeups judge/container judge/delivery judge/equivalence judge/external-references judge/fixtures judge/floating judge/hardening judge/infrastructure-stages judge/integrity judge/isolation judge/kernel-seal judge/motion judge/natural-sets judge/natural judge/old-specs judge/one-process judge/path-policy judge/preview judge/render-profile judge/require-isolation judge/rocks judge/sandbox-mounts judge/sandbox judge/shared-access judge/silhouettes judge/stage-crash judge/stage-isolation judge/textures judge/tree-bark judge/tree-species judge/validator judge/verdict judge/vertex-colours judge/visibility-sampling judge/visual-judge judge/visual-live library-blender library-textures liquid-scenes-example lsystem-example mcp-bridge-extras mcp-e2e mcp-engraving mcp-modeling-kit mcp-polish-2 mcp-recovery mcp-routing-bench mcp-textures meadow-cover-example noise-terrain-example package/package phyllotaxis-example rocks-example scatter-example session-ready session shells-example thread-independence tooling/affected tooling/codemap tooling/guard tooling/mutation-study tooling/natural-calibration-offline tooling/shared-blender tree-batch-speed tree-example tree-mesh-example tree-shape-example tree-skeleton-extras tree-species-example uv/uv-pack weather-scene-example world-scale-example world-scale-mcp

- `bridge/tests/test_<name>.py` (166 files, run inside Blender): abrade addon air_and_light animation atmosphere autosave autosave_bench autosave_recovery bake bake_failures bake_sizes boolean_cutters brass brass_ageing camera_photography camera_setup checkpoints chip clean_mesh cloud_look clouds constraints cover_budget cover_contact cover_elements cover_masks cover_review crate default_shading describe distant_forest distant_land early_counts edge_order engrave engrave_cutters engrave_many engrave_overlap engraved_union erode example_plans export_hierarchy files floating_origin fluvial_fields fluvial_network fluvial_physics fluvial_speed fluvial_terrain fracture geometry grass_light ground_cover ground_export heightfield hierarchy honey_classes images instances journal landscape_air lathe lights liquid_bodies liquid_fill liquid_optics liquid_scene liquid_state lods loft lsystem_grammar lsystem_turtle marble marble_finish material_nodes materials meadow_cover meadow_fields meadow_ground mesh_data mesh_edit modifier_kit modifiers native_dist natural_materials noise_displace noise_math objects outline_solids package_math packed_digest pbr phyllotaxis plan_checks portable_math preview procedural remesh_blob render render_final render_views render_views_copies render_views_large render_views_match render_views_surfaces rig_export rigging rock_integration rock_material rock_relief rock_shape rollback roller_chain run_python scales scatter scatter_options scene scene_info scratch_direction selection_kit shell shell_surface shell_wall shore_stones skinning sky smoke spill_rim sweep sweep_analytic sweep_closed terrain_kernels terrain_loader terrain_physics terrain_safety terrain_speed terrain_threads textured_prop tree_batch tree_colonization tree_crown tree_crown_species tree_foliage tree_form tree_habit tree_leaf_shapes tree_leaves tree_levels tree_mesh tree_shape tree_skeleton tree_species tree_strands uv_coverage uv_texel valley_mist wear weather woodland woodland_field woodland_plan woodland_shrubs world_hdri world_scale world_switch

- `bridge/tests/` helpers, not tests: autosave_helpers.py cover_helpers.py drainage.py engrave_checks.py erode_helpers.py final_helpers.py fingerprint.py fluvial_speed.py harness.py kit_helpers.py land_helpers.py limits_doc.py liquid_helpers.py lsystem_helpers.py marble_stats.py meadow_helpers.py natural_stats.py noise_helpers.py record_plans.py rig_helpers.py rock_helpers.py rock_render_helpers.py scatter_helpers.py shared.py shell_helpers.py sky_helpers.py terrain_helpers.py terrain_speed.py texture_helpers.py texture_stats.py tree_crown_helpers.py tree_helpers.py tree_mesh_helpers.py tree_shape_helpers.py view_helpers.py
