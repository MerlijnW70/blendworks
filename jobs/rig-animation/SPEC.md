# Job: Rigs, skinning and animation authored with commands

The judge checks rigs, skins and animation clips (`docs/DESIGN.md`, "Rigs, skins, animation and vertex colours"): required bones, bone limits, influences per vertex, normalised weights, rest pose, required clips, seamless loops, root motion and bounds. But the bridge cannot author any of it: there is no command to create an armature, bones, weights, shape keys or actions, so a hirer can order a character or a moving prop that no agent can deliver without `run_python`. Close that gap with commands that produce assets the judge's rig, skin and animation rules pass.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Armatures and bones:** create an armature, add, rename, parent and orient bones (head, tail, roll in metres and degrees), mirror left/right by name convention, and set deform flags; templates for a humanoid (with a documented bone map matching common names such as `Hips`, `Spine`, `Head`, `LeftHand`, and the `boneMap` style the judge uses), a quadruped and a simple prop (hinge, piston, wheel) fitted to a mesh's bounds or to named landmarks.
2. **Skinning:** bind a mesh to an armature with automatic weights, with options to limit influences per vertex (default 4), normalise, smooth, and assign rigid parts (whole loose parts or vertex groups to one bone); report unweighted vertices; keep the bind pose as the rest pose.
3. **Constraints and IK:** add IK chains (with pole targets) and common constraints (copy rotation, damped track, limit rotation) needed for posing; bake them into keys on export.
4. **Animation:** create actions/clips with keyframes on bones and objects (location, rotation, scale), interpolation and cycle settings; a procedural walk-cycle preset for the humanoid and quadruped templates (stride, speed, cadence, in place or with root motion), an idle preset, and a turn/open/spin preset for props; make clips loop seamlessly by construction (first and last pose equal); NLA tracks so several named clips export as separate glTF animations.
5. **Shape keys:** add shape keys from sculpted offsets given by vertex group and displacement, and animate their values.
6. **Export:** glTF export carries the armature, skins (joints, inverse bind matrices, at most 4 influences), and every clip with its name; the existing export options stay valid.
7. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference, a character workflow (mesh, rig template, skin, clips, export, judge), and one short clause in `src/mcp/instructions.ts` (it is at its 4096-character limit; shorten nearby wording without dropping command names).

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- A humanoid built from the template, skinned and given walk and idle clips passes the judge's `rig`, `skin` and `animation` rules with a spec like the DESIGN example (required bones via `boneMap`, `maxInfluences` 4, `normalized`, `restPose`, required clips, `loop` on walk, `maxRootMotion` for in-place walk, `boundsWithin`), through the full judge on the exported glb.
- Breaking each property (an unweighted vertex, a fifth influence, a clip whose last frame differs, a missing bone) makes the matching judge rule fail.
- Mirroring produces symmetric bones by name and position; IK reaches its target within a stated tolerance; constraints bake to keys that match the constrained pose.
- The walk cycle's foot contact: each foot's lowest point stays within a stated height band during its stance phase, and the stride length matches the parameter.
- Shape key values animate and export.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Use Blender's built-in armature, automatic weights and constraint tools through bpy; write presets and templates yourself.
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/` (rig, skin, animation, shape keys), the export command module for the glTF options, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`. The existing `rig.py` (preview camera rig) may be renamed if the name clashes, with its imports updated.
- **Files shared with other open jobs:** tree-shape owns the tree modules; judge jobs own `src/judge/**` and `bridge/judge/**` (do not change the judge's rules; only use them). If several jobs touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that builds a simple stylised humanoid and a four-legged creature from primitives and shape tools, rigs, skins and animates them (walk and idle; trot and idle), plus a prop (a chest whose lid opens), exports each, judges each with a rig/skin/animation spec, and reviews contact sheets and a few animation frames: joints bend cleanly, feet plant, loops do not pop.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
