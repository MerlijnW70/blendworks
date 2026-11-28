# Job: Cloud bases — natural undersides, near and far

The owner sees the bottoms of the clouds as too straight and unnatural. Real cumulus do have flattish bases, at the lifting condensation level. But in a photograph:
- each base sits at a slightly different height;
- it undulates and is ragged, with fractus and soft wisps;
- it fades over tens of metres rather than ending at a hard plane;
- it is darker and shaded from above;
- perspective makes far bases converge into thin, overlapping slivers, not stacked flat cards.

In Blendworks renders (for example F:/blendworks-kit/photographic-light/renders/full/*.png and the river renders in the scratchpad), the clouds near the horizon read as flat cut-off sheets with ruler-straight undersides. A known follow-up already says "flat 2D clouds in horizon_views".

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Diagnose.**
   - State which cloud form or forms the default weather uses near and far (`cloud_sheet`, `cloud_volume`, `cloud_field` layers and the `auto` choice).
   - Show where the straight bottoms come from: a 2D sheet, a hard base cutoff in the density function, one base height for the whole layer, or missing base shading.
2. **Physical bases.**
   - The base height varies per cloud around the layer's condensation level, with a cited spread (tens to about 100 m).
   - The base surface undulates at cloud scale.
   - Density rises over a stated base-transition depth, not as a step.
   - Ragged fractus and wisps hang below some bases, by a stated share.
   - The ranges come from cited cloud physics or observation (for example LCL variability and cumulus base studies).
3. **Far clouds keep their 3D shape.**
   - Clouds near the horizon render with a volumetric or volume-equivalent base: overlapping, perspective-correct undersides, and correct shading from above.
   - Where a cheaper far form is needed for speed, it must carry the same base shape and shading (for example a baked depth and normal impostor, or a thin volume), not a flat card.
   - State the render cost.
4. **Working with what exists.**
   - `weather`, `sky`, the presets and `render_final` keep working with explicit settings.
   - The defaults use the new bases.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the spread of base heights across clouds is within the cited range;
- density at the base rises over the stated depth;
- in a rendered view of horizon clouds, the cloud-bottom edges are not straight: measure the curvature or straightness of the lower edge contours, and fail on near-straight horizontal edges;
- the render time stays within a stated budget.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes:
  - no post-render masking;
  - cited ranges;
  - no per-scene tuning.
- **Allowed files:** the cloud modules (`cloud_*.py`), the weather and sky commands where they pick cloud forms, `docs/examples/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the lake example in the morning and a low view along a river toward the horizon, with `render_final` at default settings. Compared with CC0 photographs of fair-weather cumulus, the cloud bases read natural: varied height, soft and ragged, perspective-correct, not straight cut sheets.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
