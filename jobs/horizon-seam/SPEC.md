# Job: Horizon seam — near terrain and distant land are one landscape

In the lake renders the detailed near terrain reads as a floating island in front of the distant land (`distant_land`, `land_region`, `distant_forest`). The two are separate systems laid edge to edge:
- a height step or edge where the near terrain ends;
- dense grass right up to the edge, then bare, pale ground;
- no transition band;
- far land with its own shape and material that ignores the near terrain.

Make the distant land a continuation of the near terrain, not a separate landscape beside it.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **One source of truth.**
   - The distant land reads the near terrain's border: heights, slopes, drainage direction and the material and cover classes.
   - It continues them outward: macro-shape and drainage continue, and its own relief blends in over a stated distance.
   - Any terrain the scene supplies works as the near terrain (heightfield tiles, fluvial terrain, world-scale tiles).
2. **Continuous geometry.**
   - Height and slope are continuous across the join (C1 within a stated tolerance), through a blend band of stated width.
   - There are no gaps, skirts visible from the camera, or T-junction cracks between the near tiles and the region mesh.
3. **Continuous appearance.**
   - Ground cover thins by distance-based density and LOD, with no hard edge.
   - The far ground material takes its colour, albedo and roughness from the same cover classes as the near ground, so brightness and hue match across the join.
   - Shadowing and ambient occlusion are consistent: the region mesh casts and receives the same sun shadows.
4. **Working with what exists.**
   - `horizon_views`, `to_the_horizon`, `liquid_lake`, `world_scale` and `fluvial_terrain`'s horizon option use it by default.
   - Explicit settings keep working.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the height step and slope jump along the join line are under stated tolerances;
- no crack or gap is visible from sample camera positions (ray tests);
- in a rendered clay view and in a shaded view, sampled along the join line, the luminance and hue contrast across the join is no larger than the contrast between two bands on the same side;
- cover density decreases smoothly with distance.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes:
  - no fog or haze added to hide the seam;
  - no per-scene tuning;
  - the continuation is computed from the near terrain.
- **Allowed files:**
  - `distant_land`, `land_region`, `distant_forest` and the horizon and region modules;
  - the ground-cover distance and LOD parts;
  - `docs/examples/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- `grass-light` is changing the blade and leaf materials in parallel; do not edit those. Read the far-ground colour from the cover classes through a function that grass-light can later point at its canopy model.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the lake example and the horizon_views valley with `render_final` at default settings. The near and distant land read as one continuous landscape, with no island edge, step or colour break at the join.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
