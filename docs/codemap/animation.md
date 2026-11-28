# Code map: Animation and rigging

animation, clips, gaits, posing, rigs, bones, constraints, skinning, weights, shape keys. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/blendworks_bridge/ (8)

- `bones`: Armature helpers: bone name checks, mirrored names, lookup and local coordinates. | fn: side_of mirrored_name + | test: rigging
- `clips`: Animation clip helpers: names, lookup, channels and F-curve access. | fn: check_clip_name find_clip + | test: animation
- `constraint_bake`: Bakes bone constraints into keys so exported clips play the constrained pose. | fn: constrained bake_options + | test: constraints
- `gaits`: Gait planning: cycle frames, foot paths and the humanoid walk. | fn: Plan cycle_frames + | test: animation
- `motion_presets`: Motion presets: role checks, sampling and idle poses for clips. | fn: check_roles sample + | test: animation
- `posing`: Posing maths: two-bone solves, bend directions and rotation channels. | fn: rotation about + | test: constraints
- `rig_layouts`: Rig layouts: landmarks and bone points for humanoid and quadruped rigs. | fn: Frame landmark_names + | test: rig_export rigging
- `weights`: Vertex weights: read, write, smoothing and limiting. | fn: read_weights write_weights + | test: skinning

### bridge/blendworks_bridge/commands/ (5)

- `animation`: Animation commands: preset gait and motion clips, keyed clips, clip editing, inspection and poses. | fn: preset_roles check_timing + | cmd: animation_preset clip_keys clip_edit clip_info clip_pose | test: animation
- `constraints`: The ik_chain and bone_constraint commands for posing rigs. | fn: chain_of control_parent + | cmd: ik_chain bone_constraint | test: constraints
- `rigging`: Rig commands: armature_create, bone_add, bone_edit, bone_mirror, rig_template and rig_info. | fn: bone_list fit_frame + | cmd: armature_create bone_add bone_edit bone_mirror rig_template rig_info | test: rigging
- `shape_keys`: The shape_key_add command: adds a morph target from offsets. | fn: group_weights | cmd: shape_key_add | test: rig_export
- `skinning`: Skinning commands: vertex_group and skin_bind (automatic weights for an armature). | fn: unbind bind_with_blender + | cmd: vertex_group skin_bind | test: skinning
