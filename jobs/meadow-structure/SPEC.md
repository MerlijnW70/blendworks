# Job: Meadow structure — ground and grass that vary like a real meadow

Ground cover in Blendworks reads as one carpet: the same grass, height, colour and density everywhere, right up to the water. The ground material under it is uniform at mid distance. A real meadow has structure at every scale:
- tussocks and taller clumps;
- shorter grazed or trodden patches, bare soil and worn paths;
- moss in damp shade;
- flowers in drifts of one species;
- seed heads and dry stems;
- colour changes by moisture and soil over tens of metres.

Make ground and ground cover choose their structure by rules, so a meadow reads as a photograph from 2 m to 500 m.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Structure fields.**
   - The meadow is driven by smooth, seeded fields over the ground: moisture (from height, slope, curvature, flow and distance to water), soil depth, disturbance (paths, trampled and grazed patches) and shade (from trees and terrain).
   - These fields are exposed as attributes, so materials and populations can read them.
2. **Grass that varies.**
   - Height, density, colour (green to straw), clumping into tussocks, and the share of seed heads and dead stems all follow the fields.
   - Use measured or cited ranges where they exist.
   - No region looks like a uniform carpet: within any 20 m square, grass height and density vary by stated factors.
3. **Patches and paths.** The meadow contains bare and trodden patches, a worn path network that follows easy slopes between given points or the scene's features, and molehill-like soil spots, all by rules and at stated densities.
4. **Flowers in drifts.**
   - Flowering plants grow in clusters of one species, with stated cluster sizes, not as even confetti.
   - The species follow moisture: buttercups in damp ground, for example.
5. **Moss and damp ground.** Moss and darker, denser ground cover grow in damp, shaded ground. Dry, exposed ground is sparser and paler.
6. **Ground material without tiling.**
   - The soil and the material under the grass vary at macro (100 m), meso (1–10 m) and micro (cm) scale, driven by the same fields.
   - No visible repetition at any distance.
   - At mid distance, where cover thins out, the material carries the meadow's colour structure, so the mid ground is not flat green.
7. **Working with what exists.**
   - `ground_cover` presets (meadow and others) use the fields.
   - `liquid_body` shores, trees and rocks feed moisture, shade and obstacles.
   - Distant land continues the colour structure.
   - `render_final` renders it at its default settings.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the fields respond to height, flow, distance to water and shade as stated;
- height and density vary within any 20 m square by the stated factors;
- flower clustering is measured (pair correlation or nearest-neighbour index) and differs from random;
- paths follow lower slopes than random lines;
- moss is denser in damp shade than in dry sun;
- a tiling measure stays under a stated value at three distances;
- the same seed repeats.

Small renders, CPU.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- Blendworks builds everything itself.
- No quick fixes: everything is rule-driven in general code, with no hand-painted patches.
- **Allowed files:**
  - the ground-cover modules and commands (`cover_*`, `ground_cover`);
  - the ground and grass material presets;
  - new modules for the structure fields;
  - the scatter mask code where fields plug in;
  - `docs/examples/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the lake example (`docs/examples/liquid_lake.py` with `BLENDWORKS_HORIZON=rolling`) at default `render_final` settings, from its two cameras and one new low meadow camera. Compared with CC0 photographs of a summer meadow by a lake, the meadow reads as real ground with structure, not as a carpet.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
