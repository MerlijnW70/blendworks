# Job: Judge rules for natural assets, calibrated on real scans

The judge can check size, topology, textures and silhouettes against a reference, but nothing tells a displaced sphere from a rock or a cylinder tree from a shrub. `docs/research/natural-shapes.md` (sections 2, 2.7 and 5) defines measures that separate them, with starting thresholds from a small sample of 10 rocks, 1 shrub set and 4 stand-ins. Build the first four `natural` rules (plan item P11, job A) and the calibration set (P12) that sets their thresholds from 30 or more real CC0 scans.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Calibration set (P12):**
   - A script, `npm run calibrate:natural`, downloads at least 30 CC0 models from Poly Haven (rocks, trees and logs, plants and shrubs, at least 8 of each class) through the existing library client, into the library cache. Nothing downloaded is committed.
   - It builds the stand-ins of section 2.7 (UV sphere, clouds-displaced ico sphere, jittered ico sphere, cylinder tree) and, when the commands exist on `main`, procedural assets made with `noise_displace`, in headless Blender by script.
   - It runs the four measures below on every model and writes `docs/research/natural-shapes/calibration.json` (per asset: id, class, source URL, licence, every measured value) and a percentile table per class (5th, 25th, 50th, 75th, 95th) into `docs/research/natural-shapes.md`.
   - Thresholds are derived by a stated rule (for example the 5th percentile of the real class, or the midpoint between the real 5th percentile and the worst stand-in when they do not overlap), and the separation of real assets from stand-ins is reported per rule. Where a measure does not separate them, say so and do not make it a default rule.
   - The run is reproducible: the model list and resolutions are pinned in the script, and a second run gives the same values.
2. **Rules (P11 job A),** an optional `natural` group in the asset spec, measured inside the existing judge sandbox and run:
   - `natural.silhouetteDimension`: box-counting `D` of the silhouette edge, front and right views, 1024 px, boxes 2–64 px, from the silhouettes the reference stage already renders.
   - `natural.solidity`: silhouette area over convex hull area, lowest over front, right and top.
   - `natural.surfaceRoughness`: per object, the angle between each sampled face normal and the area-weighted mean normal within `extent/32` (KD-tree of face centres, a fixed number of area-weighted samples, deterministic), 90th percentile and the share under 3°.
   - `natural.albedoVariation`: luminance coefficient of variation of base-colour texels in the used UV area (texels with luminance > 0.02, or inside the UV islands).
   - Each rule takes explicit limits in the spec; their defaults come from the calibration, and `docs/DESIGN.md` documents each measure, its default and the calibration it came from.
   - Rules follow the existing pattern: a measurement that cannot be made reports `null` and fails, values are in the report and in `blendworks diff`, and the one-process judge keeps its single pass and stage isolation.
3. **Visual rubric template:** a documented spec template for natural assets with the rubric criteria of section 5 (`no-primitive`, `multi-scale`, `no-repetition`, `weathering`, `material-variation`), used beside the measured rules.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Box-counting `D` of analytic shapes rendered as masks: a circle gives `1.00 ± 0.05`; a Koch snowflake at enough depth gives `log 4 / log 3 ≈ 1.262 ± 0.05`.
- Solidity: a square gives 1; an L-shape of known area gives its area over its hull area, worked out by hand.
- Surface roughness: a sphere gives a p90 under 5° and a flat share above 0.9; a cube gives a flat share near 1 and a p90 of 0; the clouds-displaced ico sphere fixture fails the calibrated rock default.
- Albedo variation: a constant-colour texture gives 0; a two-tone texture with known proportions gives the CV worked out by hand.
- Each rule passes a generated fixture that should pass and fails one that should fail, through the full judge.
- The calibration script has an offline test on generated stand-ins (no network), checking the table format and the threshold rule.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`.
- CC0 data only (Poly Haven); downloaded files stay in the cache and are never committed. Record each asset's source page and licence in `calibration.json`.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `schemas/**`, `scripts/**`, `test/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`, `package.json` scripts.
- **Files shared with other open jobs:** noise-terrain owns new bridge command modules, `src/mcp/**` and `bench/**`; do not touch them. The job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs `npm run calibrate:natural` and gets the committed table; then judges two downloaded scans and two stand-ins with a natural spec built from the defaults, and sees the scans pass and the stand-ins fail.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
