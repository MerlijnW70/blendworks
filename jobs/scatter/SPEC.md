# Job: Scatter instances over a surface with Poisson disk spacing

Blendworks can place instances at given points or along paths (`instances`), but it cannot sample a surface. Rubble on a slope, stones on terrain, plants on a ground tile all need natural spacing, masks and size distributions, without the visible repetition of a grid. Build `scatter` (plan item P4 in `docs/research/natural-shapes.md`) from the cited papers.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`scatter` command:**
   - Parameters: `target` (mesh), `source` or `sources` (with weights), `min_distance` (metres), `density` (per m², a cap); `density_mask` (`slope`, `height`, `vertex_group`, `noise`, `attribute`, combined by multiplication) with `slope_range`, `height_range` and a named float attribute (such as those `heightfield` writes); `scale_range` and `scale_distribution` (`uniform`, `lognormal`, `power` with `exponent`, default −2); `align` (`normal`, `up`, `blend` with a factor), `random_yaw`, `tilt`; `seed`, `max_count` (at most the bridge's instance limit), `realize`; `embed` (sink each instance by a fraction of its height so it does not float on slopes).
   - Sampling is Poisson disk on the surface in world metres: Bridson's dart throwing with `k = 30` in the annulus `[r, 2r]` [S37], or area-weighted candidates thinned to a minimum distance [S38]. Distances are measured in 3D on the surface, so spacing holds across faces and on steep slopes.
   - With a `power` distribution, `min_distance` scales with each instance's size (variable-radius disk), so large pieces do not overlap and small ones fill the gaps.
   - Deterministic by seed and independent of face order; placement goes through the existing `instances` machinery (collection instances or realized meshes).
   - The reply reports the count, the smallest pairwise distance, the masked-out share and the size histogram.
2. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference, `src/mcp/instructions.ts` and a workflow for scattering on terrain.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- The smallest pairwise distance between instances is at least `min_distance` (exact check over all pairs), on a plane and on a `heightfield` tile with steep slopes.
- With a variable radius, no two instances are closer than the sum-based rule you state.
- No instance sits on a face whose slope is outside `slope_range`, or where a named attribute is below its threshold.
- On a 10 m × 10 m plane with `min_distance` 0.5 the count is at least the density of a maximal Poisson disk packing you derive and cite, and the regression value of a fixed seed is pinned.
- The repetition peak of a top-view splat (section 2.7 method of the research document) is at most 0.2, while a jittered grid exceeds it.
- The fitted exponent of the size distribution with `power` −2 is within ±0.2 of −2 over 2,000 samples.
- The seed is deterministic and shuffling face order changes nothing.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write the methods from the papers; do not copy GPL add-ons.
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, `instancing.py` and `commands/placement.py` where reuse needs it, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** natural-rules owns `src/judge/**`, `bridge/judge/**`, `schemas/**` and `scripts/**`; natural-materials owns `presets.py`, the material modules and `commands/materials.py`, `commands/procedural.py`. If both of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that scatters a rock set with a power-law size distribution and an embed over a `heightfield` tile, masked by slope, and reviews the renders: natural spacing, no floating or interpenetrating pieces, no visible pattern.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
