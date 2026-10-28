# Job: Phyllotaxis: seeds, petals, scales and leaves in the golden-angle arrangement

Sunflower heads, daisies, pine cones, succulents and leaf rosettes all place their organs by one rule: the n-th organ sits at angle `n · 137.5°` and radius `c · √n` (on a disc), or climbs a cylinder or cone with the same divergence. Blendworks can place instances at given points, but an agent would have to compute the pattern by hand. Add phyllotaxis to `instances` (plan item P8, first half, in `docs/research/natural-shapes.md`), after Vogel's model and *The Algorithmic Beauty of Plants* [S1, S31].

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`instances` gains `phyllotaxis`:**
   - Parameters: `count`, `c` (metres), `divergence` (default 137.5°, or `golden` for the exact `360° · (1 − 1/φ)`), `mode` (`disc`, `cylinder`, `cone`, `sphere`, `surface` with a target mesh of revolution), `height` and `radius` for the cylinder and cone, `start` (first index), `scale_by_age` (organs grow with index, with a curve), `tilt_by_age` (organs open outwards with age, as petals and scales do), `align` (to the surface normal or radially).
   - Formula: on a disc `r = c√n`, `φ = n · divergence` [S1, S31]; on a cylinder a constant radius and height growing linearly with `n`; on a cone and sphere, spacing that keeps the organ area constant (state the formula you derive).
   - Deterministic, no randomness unless an optional `jitter` with a seed is given.
   - Organs are placed through the existing instance machinery (instances or realized), within the bridge's instance limit.
2. **Routing, docs and MCP:** the command reference, schemas and `src/mcp/instructions.ts` cover it; held-out benchmark intents for phyllotaxis requests (sunflower head, pine cone, succulent rosette) without lowering the benchmark floors.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- On a disc, the angle between successive instances is the divergence to 1e-9 and the radii are `c√n` to 1e-9.
- With `golden`, the visible spiral (parastichy) counts are consecutive Fibonacci numbers: counting nearest-neighbour spirals in a 1,000-seed disc gives a pair such as (21, 34) or (34, 55); derive and assert the expected pair for the tested range.
- On a cone and a sphere, the area per organ stays within a stated tolerance across the arrangement.
- `scale_by_age` and `tilt_by_age` follow their curves at sampled indices.
- Without `jitter` the result is identical every run; with `jitter` a fixed seed repeats.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the papers and the book.
- **Allowed files:** `bridge/blendworks_bridge/instancing.py`, `commands/placement.py`, new modules under `bridge/blendworks_bridge/`; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** other open jobs own their new command modules; if several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that builds a sunflower head (seeds on a disc, petals around it), a pine cone (scales on a cone, opening with age) and a succulent rosette (leaves on a sphere or surface), with materials, and reviews the renders.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
