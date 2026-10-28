# Job: Tree skeletons by space colonisation and recursive levels, with roots and pipe-model radii

Trees are the hardest natural asset for an agent: a branching structure with radii that thin by a law, a crown that fills an envelope, and roots. Blendworks has no way to grow one. Build the skeleton half of `grow_tree` (plan item P5, job A in `docs/research/natural-shapes.md`), from the cited papers. A later job turns the skeleton into a mesh; this job delivers the skeleton, its radii and a preview so it can be judged on its own.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`grow_tree` skeleton:**
   - `method` (`colonization`, `levels`).
   - Colonisation [S2]: `envelope` (a mesh object, or a built-in crown shape from the Weber–Penn `Shape` table [S3]: conical, spherical, hemispherical, cylindrical, tapered cylindrical, flame, inverse conical, tend flame), `points` (N), `influence` (`di`), `kill` (`dk`), `step` (`D`), `tropism` (vector `g`), `trunk_height`, `seed`. Each step as in the paper: a point influences only its nearest node within `di`; a node with influencing points grows a new node at distance `D` towards the normalised sum of unit vectors, biased by `g`; points closer than `dk` are removed.
   - Levels [S3]: `levels`, `branches`, `down_angle`, `rotate` (default 137.5°), `length_ratio`, `ratio_power`, `curve`, `taper`.
   - `roots`: a second skeleton grown in a soil envelope below the trunk base with downward tropism, joined at the base.
   - Radii by the pipe model `r^n = Σ r_i^n` from the tips down, `n` default 2 (range 1.8–3) [S2, S53], with a `tip_radius`.
   - Hard caps on nodes and points, checked before growth, with a clear message.
2. **Output:** the skeleton (nodes with position, parent, radius and order) stored on the object as a custom property and in glTF `extras` on export, so the judge can read it later for `natural.leonardo`; returned in the reply in pages; and a preview object (a curve with bevel by radius, or thin tubes) so it can be seen and rendered now.
3. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference and `src/mcp/instructions.ts`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Every attraction point within `dk` of a node is removed when growth ends, and no node lies outside the envelope by more than `D`.
- At every branching node `|r^n − Σ r_i^n| / r^n < 1e-6`, for `n` = 2 and 2.5.
- With `levels`, consecutive children differ in rotation by `rotate` to 1e-9, and child lengths follow `length_ratio`.
- Tropism: with a downward `g`, the mean branch direction tilts down compared with `g = 0` (stated measure).
- The skeleton is a tree (one root, no cycles), roots lie below the base and the trunk above.
- The seed is deterministic and independent of point order.
- The skeleton survives a glTF export and re-import in `extras`, node for node.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the papers; do not port Sapling (GPL-3.0-or-later) [S5] or tree-gen (GPL-3.0) [S9].
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, the export command module for writing `extras`, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** other open jobs own their new command modules; if several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that grows three skeletons (a broad oak-like crown by colonisation with roots, a conical conifer by levels, a wind-bent tree with tropism) and reviews the preview renders: branches fill the crown, thin towards the tips, and do not cross.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
