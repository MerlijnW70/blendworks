# Code map: Bridge core

handler, registry, schema, policy, limits, util, workspace, plan, validate, autosave, scene, files, checkpoints, images, exports, session and add-on. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/ (2)

- `build_addon`: Builds the installable add-on zip from the add-on folder and the bridge package. | fn: addon_files build +
- `session`: The headless Blender session: reads requests from the protocol stream and serves them. | fn: take_protocol_stream parse_arguments + | test: addon

### bridge/addon/ (2)

- `__init__`: Blender add-on entry point: preferences, and start and stop of the bridge server inside a desktop Blender. | fn: launch_options preferences + | test: addon
- `server`: Threaded socket server of the desktop add-on: queues each client's requests and runs them on Blender's main thread. | fn: stopped_reply Job + | test: addon

### bridge/blendworks_bridge/ (35)

- `__init__`: Blendworks bridge package: the command registry and handlers that run inside Blender.
- `autosave`: Autosave of the headless session: interval from the environment and the journal of replayable commands. | fn: interval_from_environment now_text + | test: autosave autosave_bench +1
- `blendfile`: Atomic saving of .blend files and the data blocks that are unused or unsaved. | fn: looks_like_blend partial_path + | test: autosave checkpoints +2
- `device`: Render device choice: GPU backend probing, mode selection and a scope that applies it. | fn: requested_mode cycles_preferences + | test: render
- `errors`: The bridge's error class and the constructors for bad arguments, not found, failed and forbidden. | fn: BridgeError bad_args + | test: bake_failures engrave +1
- `exporting`: Export option checks and preparation for glb, fbx and obj exports. | fn: option_fields check_options + | test: autosave checkpoints +2
- `exr_read`: Minimal OpenEXR header and part reader. | fn: ExrError Part + | test: air_and_light camera_photography +8
- `gltf_extras`: Reads and writes glTF files to add skeleton extras. | fn: skeleton_extras read_glb + | test: autosave checkpoints +2
- `handler`: Request handler: validates a request, runs a command in a context and encodes the reply. | fn: Context Handler + | test: crate describe +2
- `image_header`: Reads image dimensions from PNG, JPEG, WebP and EXR headers without loading pixels. | fn: image_dimensions dimensions_of + | test: images
- `images`: Image helpers: colour space keys, size checks, lookup and loading. | fn: colorspace_key is_data + | test: images
- `inspect_scene`: Scene inspection: totals, collections, matching objects and paged listings. | fn: Listing totals + | test: describe scene_info
- `journal`: Journal files of the autosave: line encoding, hashes and change detection. | fn: journal_name encode_line + | test: journal
- `kit_limits`: Data table of the limits of the modelling kit tools. | test: tree_foliage tree_leaves +1
- `limit_base`: The named limit type: a number that knows its name, unit, kind of reason and reason. | fn: FloatLimit IntLimit + | test: world_scale
- `limits`: Every limit a tool schema uses, each with the reason for its value. | fn: parse_cgroup_limit physical_memory + | test: autosave cover_review +5
- `limits_fluvial`: Limits of the fluvial terrain tool. | test: fluvial_terrain
- `limits_land`: Limits of the distant land, forest, impostor and valley mist tools. | test: distant_land
- `limits_meadow`: Limits of the meadow fields. | test: meadow_cover
- `limits_parts`: Named limits of the shape, terrain, tree, scatter and liquid tools (commands a to l). | test: world_scale
- `limits_parts_more`: Named limits of the material, mesh, render, rig and weather tools (commands m to z). | test: world_scale
- `limits_woodland`: Woodland limits. | test: woodland
- `meshdata`: The MeshData container of vertices, faces and UVs. | fn: MeshData | test: engrave_cutters
- `operators`: Contexts for running Blender operators: window, selection and edit mode. | fn: window_context operator_context + | test: mesh_edit
- `plan`: Check a list of calls without running any of them. | fn: PlanState references + | test: plan_checks world_scale
- `policy`: The Policy of a command: whether it mutates, is slow, snapshots or is internal. | fn: Policy | test: autosave checkpoints +2
- `portable_math`: Math functions with the same results on every platform. | fn: ratio acos | test: portable_math
- `registry`: The command registry: the command decorator, routing metadata and the COMMANDS table. | fn: Routing Command + | test: describe render_final +1
- `schema`: Schema builders for command arguments: number, length, integer, string, vector3 and so on. | fn: number length + | test: phyllotaxis world_scale
- `selection`: Face selection by selectors: islands, area, material and refine. | fn: has_selector face_islands + | test: objects
- `transaction`: Transactions: undo steps around a command so a failure rolls back. | fn: NoSnapshot Transaction + | test: mesh_edit
- `transport`: Wire protocol helpers: reads a request and builds the too-long and quit replies. | fn: read_request too_long_reply + | test: addon smoke
- `util`: Shared helpers: rounding, vectors, degrees, object lookup and free-name checks. | fn: rounded vec + | test: early_counts phyllotaxis +1
- `workers`: Child Blender sessions that run bridge commands in parallel. | fn: read_text cgroup_cpus + | test: tree_batch
- `workspace`: The workspace folder: resolves and checks every file path. | fn: Workspace | test: files

### bridge/blendworks_bridge/commands/ (7)

- `__init__`: Imports every command module so each registers its commands in the registry. | fn: load
- `checkpoints`: The checkpoint, restore_checkpoint and recover commands: named scene snapshots and autosave recovery. | fn: checkpoint_folder checkpoint_path + | cmd: checkpoint restore_checkpoint recover | test: checkpoints
- `files`: The export, save_blend, load_blend and import commands: scene files in the workspace. | fn: with_rigs chosen_objects + | cmd: export save_blend load_blend import | test: files
- `images`: Image commands: load, create, save and inspect images in the workspace. | fn: plan_image_load write_image + | cmd: image_load image_new image_save image_info | test: images
- `run_python`: The run_python command: runs arbitrary Python inside Blender, a dangerous escape hatch. | fn: plan_run_python json_value | cmd: run_python | test: run_python
- `scene`: Scene commands: describe, scene_info, new_scene, select and delete. | fn: reset_scene purge_unused + | cmd: describe scene_info new_scene select delete | test: scene
- `validate`: The validate command: checks a call or a plan of calls against the schemas without running it. | cmd: validate | test: world_scale
