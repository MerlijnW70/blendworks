# Job: Fluvial core — mountain ranges carved by rivers

The terrain kernels (`native/`, `terrain_kernels`) are on `main`. Build the first terrain stage on them: an uplifted range eroded by implicit stream power, with lake routing and hillslope diffusion, at 30–60 m cells over tens of kilometres. It should give dendritic drainage, a ridge hierarchy and valleys that obey the published scaling laws.

The research is in F:/blendworks-kit/terrain-research/REPORT.md (copied into the repo as `docs/research/terrain-core.md` if missing).

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Model.**
   - An uplift field: a block or range shape, a tilted or domed field, or a user array.
   - Implicit stream-power incision (Braun & Willett 2013) with erodibility K, m/n and an optional spatial K field from lithology bands.
   - Lake routing in carving or filling mode.
   - Linear or non-linear hillslope diffusion.
   - Base level on chosen edges: one edge, two edges or all.
   - All on the terrain kernels. The Python layer only orchestrates.
2. **Spin-up.**
   - Coarse-to-fine: run to near steady state at a coarse grid, upsample, then refine.
   - Time steps are chosen for stability and stated. The run stops on a steady-state criterion or a step budget.
3. **Outputs.**
   - The height grid.
   - Drainage area, the flow receivers, the channel mask by area threshold, and Strahler order.
   - Lake depth, and a per-cell erosion or deposition record.
   - These are returned as arrays and as mesh attributes or images that the later stages (glacial, amplification, materials) and scatter masks can read.
4. **Tool.**
   - A command `blender_fluvial_terrain` (or an extension of `heightfield`), with parameters in physical units: years, m/yr, km.
   - Presets for young alpine, mature mountain and dissected plateau, from cited parameter ranges.
   - It builds a terrain mesh with LOD tiles through the existing world-scale and horizon tools.
5. **Working with what exists.**
   - `erode` stays as is.
   - `heightfield`, `world_scale`, `horizon_views`, scatter masks and liquids (rivers and lakes on the channel and lake outputs) can consume the result.

## Targets

- 2048² cells at 30 m (61 km) in at most 120 s of CPU on 4 threads, including spin-up.
- Zero undrained pits after routing, except lakes.
- Hack exponent 0.5–0.6 over at least 1.5 decades of area.
- Trunk Strahler order at least 6 at 60 km with base level on one edge.
- Aspect distribution share 0.50 ± 0.05, as in the research.
- A clay hillshade reads as dendritic mountain terrain, not noise or combs.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the analytic steady-state slope–area relation;
- no pits;
- Hack's law;
- the Strahler order;
- the time budget, by the speed guard;
- the presets within their cited ranges;
- the outputs are consumed by scatter masks and liquids.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes: physics from the papers, cited parameter ranges, no noise passed off as erosion.
- **Allowed files:**
  - new bridge modules and the new command;
  - additive changes to `terrain_kernels` callers, but not to the kernels themselves except for bug fixes with tests;
  - `docs/examples/**`, `bench/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders, with `render_final` at default settings:
   - a clay hillshade from above of the young alpine preset at 60 km;
   - an oblique view at eye level.

   Compared with real DEM hillshades of similar ranges, the first shows dendritic drainage and a ridge hierarchy.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
