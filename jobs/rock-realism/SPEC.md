# Job: Rock realism — stones that read as stone at one metre

Shore stones and boulders in Blendworks look smooth, soft and almost alien. The causes:
- **No real surface relief:** there is no grain, pits, cracks or rough fracture faces; only a colour pattern lies on a smooth surface.
- **Over-abraded shapes:** soft rounded forms with flat facets.
- **One uniform grey:** no mineral speckle, weathering rind, lichen or waterline staining.
- **A plastic sheen:** dry rock shines.

Make rocks read as photographs of real stones at 1 m, 10 m and 50 m.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Surface relief.**
   - Rock surfaces get real geometric relief: grain at millimetre scale, pits, hairline cracks, rough fracture faces and worn edges.
   - It is applied as render-time displacement with adaptive subdivision near the camera (Cycles), and as normal or bump detail at distance.
   - Amplitudes and scales come from the lithology, with cited or measured ranges where they exist.
   - Detail falls off with distance within a stated triangle and memory budget.
2. **Shape history.**
   - Stones combine fresh fracture faces (sharp, planar to conchoidal) with abraded convex edges in proportions set by their transport history.
   - Abrasion acts on edges and corners first (curvature-driven), never as uniform smoothing.
   - No soft "pillow" shapes.
   - Shape statistics (roundness, sphericity and flatness) follow stated ranges for each history class: angular talus, subrounded shore, rounded river cobble.
3. **Lithology materials.**
   - Granite: mineral speckle of feldspar, quartz and mica, at stated grain sizes.
   - Sandstone: bedding, colour bands and grain.
   - Limestone: pale, with solution pits.
   - Basalt: dark, fine and vesicular.
   - Colours and roughness come from cited reflectance or measured ranges.
   - Dry rock is matte.
4. **Weathering.**
   - Lichen grows in patches, crustose and foliose, with stated coverage on exposed faces. Moss grows in cracks and on shaded or damp tops.
   - A weathering rind changes colour.
   - At water: a wet dark band, algae below the waterline, and a tide or water mark.
   - Specular reflection is high only where the rock is wet.
   - All of these are driven by the existing `weather` wetness and the `liquid_body` level.
5. **Working with what exists.**
   - `fracture`, `chip`, `abrade`, `shore_stones`, `scatter` rocks and the stone presets use this.
   - Existing callers keep working.
   - `render_final` renders at its default settings within the judge's memory.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- displacement amplitude near the camera is at least a stated value, and zero far away;
- each history class's roundness and flatness fall in their stated ranges;
- abrasion removes more from high-curvature vertices than from flat ones;
- the speckle statistics of granite (grain size and contrast) fall within stated ranges;
- lichen covers more of exposed tops than of undersides;
- wet rock is darker and more specular than dry rock by stated factors;
- the budgets hold.

Small renders, CPU.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- Blendworks builds every rock itself, with no scans.
- No quick fixes: general code with cited or measured ranges, and no hand tuning per scene.
- **Allowed files:**
  - the rock tools (`fracture`, `chip`, `abrade` and their modules);
  - `shore_stones` and the stone shape and plan modules;
  - the stone and rock material presets;
  - new modules for rock detail and weathering;
  - `render_final` only where adaptive subdivision needs settings;
  - `docs/examples/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders, with `render_final` at default settings:
   - the lake example's shore close-up;
   - a 1 m close-up of a granite boulder;
   - a sandstone ledge;
   - a river cobble bed.

   Compared with CC0 photographs of the same rocks, each reads as real stone.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
