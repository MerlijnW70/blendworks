# Job: Bank form — ground that is uneven, cut and worn like real terrain

Near the camera, Blendworks terrain reads as smooth rounded noise: soft hills with no breaks. Real ground, and above all a riverbank, is uneven and damaged:
- **outer bends:** cut banks, undercut and slumped, with fresh soil faces;
- **inner bends:** point bars of gravel and sand;
- **the water's edge:** small steps and terraces;
- **slopes:** rills and gullies, plus slump scars and collapsed edges;
- **grassland:** tussock hummocks and animal paths;
- **everywhere:** centimetre-scale roughness.

The owner sees the near terrain as "too round". This job builds the terrain shape: the geometry, not the cover.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **River bank geomorphology from the channel.**
   - On meander bends, from the river path's curvature: cut banks on the outer bank (steep to undercut, with a stated height range) and point bars on the inner bank (low gradient, from cited ranges).
   - Small terraces and steps at the water's edge.
   - Slump blocks and collapse scars on cut banks, by a seeded process with stated rates.
   - Built from `liquid_body` river paths and the carve, so every river gets them.
2. **Hillslope damage.**
   - Rills and small gullies follow flow accumulation on the terrain, using the native terrain kernels.
   - Bare scars where slopes exceed stability.
   - Tussock and hummock micro-topography on grassland and wetland, from cited sizes and spacing.
   - Optional animal and foot paths.
3. **Near-camera micro-relief.**
   - Centimetre to decimetre relief of the ground near the camera by adaptive displacement (Cycles adaptive subdivision, as `rock_relief` does for rocks), with bump only at distance, within a stated triangle and memory budget.
   - The amplitude is driven by the surface class: soil, gravel, mud and turf.
4. **Undercut overhangs.** Where a cut bank is undercut, the overhang is real geometry (a separate bank-lip mesh or a volume) and is not lost to the heightfield.
5. **Working with what exists.**
   - `heightfield`, `liquid_body`, `fluvial_terrain`, `ground_cover` and `shore_stones` work on the new terrain.
   - The examples use it by default.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the outer bank of a bend is steeper than the inner bank by a stated ratio;
- point bars lie on inner bends;
- rills follow flow accumulation;
- the near-camera displacement amplitude falls with distance and stays within budget;
- an undercut produces overhanging geometry;
- a roughness measure of the near ground (for example a height-variance spectrum) lies in cited ranges for the surface class, not the smooth fBm of the old terrain.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes:
  - processes from cited geomorphology;
  - no noise passed off as erosion;
  - no per-scene tuning.
- **Allowed files:**
  - `liquid_river.py` and the river carve;
  - the heightfield command;
  - new terrain-shaping modules;
  - `render_final` only where adaptive subdivision needs settings;
  - `docs/examples/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- `grass-light`, `horizon-seam`, `cloud-bases` and the coming `riparian-ground` (cover, sediment and litter) run in parallel; keep to the terrain shape.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders a low close view along a meandering river bank, using the river script in the worker brief, and the lake example's shore, with `render_final` at default settings, in clay and shaded. Compared with CC0 photographs of small river banks, the ground reads uneven, cut and worn, not smooth or round.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
