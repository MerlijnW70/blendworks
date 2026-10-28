# Job: Tree form: weeping, gnarled and wind-bent trees

`grow_tree` grows skeletons by space colonisation and by Weber–Penn levels, with one tropism vector for the whole tree and a per-level `curve`. That gives upright crowns and a tree that leans as a whole, but not the forms people recognise first: a weeping willow whose thin twigs hang while its trunk stands, a gnarled old oak with a twisting, kinked trunk, or a coastal tree whose trunk and crown are bent by a prevailing wind. Add form controls to `grow_tree` and its meshing, from the cited papers.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Order- and size-dependent tropism (both methods):** gravitropism that grows with branch order and with thinness (for example a weight per order, or a function of the node's pipe-model radius), so thin, long branches droop while the trunk and scaffold limbs stay up; phototropism towards a direction; an optional `stiffness` that lets heavy branches bend under their own length. Weeping must arise from these settings, not from a special case.
2. **Weber–Penn curvature variation (levels):** `curve_back` (an S-bend: the second half of a stem bends back) and `curve_variation` (seeded random bend per segment), per level [S3].
3. **Trunk and branch irregularity (both methods):** seeded `gnarl` (smooth noise displacement of nodes perpendicular to the stem, in metres, amplitude scaled by radius and order), `twist` (rotation of the branching frame along the trunk), and kinks (`kink_probability`, `kink_angle`). Pipe-model radii and the skeleton format stay valid (version 1, or version 2 with a documented migration if the format must change).
4. **Wind:** a `wind` vector and profile that bends the trunk progressively with height and streams the crown downwind, distinct from a uniform lean.
5. **Presets:** `weeping_willow`, `gnarled_oak`, `windswept_coastal` (plus the existing behaviour as the default), each documented with its parameters.
6. **Docs and MCP:** the command reference, schemas, the tree workflow and one short clause in `src/mcp/instructions.ts` (it is at its 4096-character limit).

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Order-dependent gravitropism: the mean direction of order ≥ 2 tips points below horizontal while the trunk's top stays within a stated angle of vertical; with the weight set to 0 the tips point up.
- `curve_back` produces a sign change in curvature along a stem; `curve_variation` with a fixed seed repeats, and the bend spread matches the parameter within a stated tolerance.
- `gnarl` displaces trunk nodes by at most the stated amplitude and keeps parents before children; `twist` rotates successive branch frames by the stated rate.
- Wind: the trunk's lean grows with height (monotone over sampled heights) and the crown centroid moves downwind; a uniform lean does not show the growth.
- Pipe-model radii still hold at every branching (`pipe_error` < 1e-6) for every preset.
- Seeds are deterministic for every new parameter.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the papers; do not port Sapling (GPL-3.0-or-later) or tree-gen (GPL-3.0).
- **Allowed files:** the tree modules (`tree_*.py`, `commands/trees.py`), the tree meshing modules if form changes need them, `gltf_extras.py` for a format version change, `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** none expected; if another job lands first, rebase.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that grows, meshes and leafs a weeping willow, a gnarled old oak and a wind-bent coastal tree, and reviews the renders: each is recognisable as its kind at a glance.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
