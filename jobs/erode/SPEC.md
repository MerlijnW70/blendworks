# Job: Thermal and hydraulic erosion of terrain

`heightfield` makes terrain from noise, but noise alone has no valleys cut by water, no talus slopes and no deposits; it reads as raw fractal relief. Build `erode` (plan item P3 in `docs/research/natural-shapes.md`), from the cited papers, working on heightfield tiles and keeping tiles joinable.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`erode` command:**
   - Parameters: `name`, `mode` (`thermal`, `hydraulic`, `both`), `iterations`, `seed`; thermal: `talus_angle` (degrees), `rate`; hydraulic: `droplets`, `inertia`, `capacity`, `min_capacity`, `erode_rate`, `deposit_rate`, `evaporation`, `gravity`, `radius`, `max_lifetime`, with Lague's values as defaults [S13]; `mask` (vertex group or a named attribute).
   - Thermal: moves material to lower neighbours where the slope exceeds the talus angle [S10]. Hydraulic: droplets carry sediment up to a capacity that grows with slope and speed (`C = Kc · sin(α) · |v|`, [S12]) and deposit it when they slow or evaporate [S11, S13].
   - Works on the heightfield grid in numpy, in world metres, so the result does not depend on the grid resolution beyond its sampling. It refuses meshes that are not a heightfield grid (as `heightfield` builds them), with a clear message.
   - **Tiles:** the edge heights of a tile stay unchanged unless the caller passes the neighbouring tiles together (`names`, eroded as one grid and written back), so tiles still join exactly.
   - Writes `erosion` and `deposition` float attributes (metres removed and added per vertex) for material masks, and updates the `slope`, `height` and `curvature` attributes if present.
   - The reply reports eroded and deposited volume, the volume carried off the edge, and the time taken.
2. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference, `src/mcp/instructions.ts`, and the terrain workflow.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Thermal: the sum of heights before and after differs by less than 1e-6 of the volume; after erosion to convergence no slope exceeds `talus_angle + 0.5°`.
- Hydraulic: eroded = deposited + carried off the edge, to a stated tolerance.
- A single droplet on a two-slope ramp erodes on the steep part and deposits where the slope flattens, worked out by hand.
- The same seed gives identical heights; another seed differs.
- Halving the grid spacing keeps the eroded volume of a fixed terrain within a stated tolerance (resolution independence in metres).
- Edge heights of a single tile are unchanged; two tiles eroded together still share their edge heights to 1e-9.
- The `erosion` and `deposition` attributes add up to the reported volumes.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the papers; Lague's repository is MIT, so a port with its copyright notice is allowed [S13]. Do not port A.N.T. Landscape (GPL) [S14].
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, `terrain.py` and `mesh_attributes.py` where reuse needs it, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** other open jobs own their new command modules; if several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that erodes a 2 × 2 tile set from `heightfield` (both modes), dresses it with materials masked by `erosion`, `deposition` and slope, and reviews the renders: drainage channels, talus and deposits that read as natural, and no seams between tiles.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
