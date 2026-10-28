# Job: Natural rules that measure what they claim and resist gaming

The natural rules separate real scans from stand-ins on honest assets, but a security audit and later jobs found weaknesses: `natural.surfaceRoughness` takes every triangle within the radius whatever its normal or connectivity, so a sphere solidified into a thin wall scores a p90 near 180 degrees, and micro-jitter under smooth shading scores rough while rendering smooth; it depends on tessellation density; on trees it barely measures bark (a crude five-segment build passes); solidity and silhouette dimension compare a `max` limit against the lowest view, which is the lenient direction; and the calibration has no adversarial stand-ins and no confidence intervals.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Roughness redesign:** neighbourhoods use only connected, outward-visible faces in the sample's hemisphere; the measure is made at a fixed geometric scale (resampled surface or plane fits at two radii) so tessellation density does not change it; a gap between shipped shading normals and geometric normals is measured and flagged; documented with the formula.
2. **Aggregation:** `max` limits compare the highest view, `min` limits the lowest view, for every per-view natural measure.
3. **Bark measure:** a measure that reflects bark relief and branch surface quality on tree meshes (for example roughness restricted to the trunk and limbs above a radius, or a fissure-depth statistic from the bark mesh), calibrated on the tree mesh examples and on scans, made a default only if it separates good bark from smooth tubes.
4. **Adversarial calibration:** the calibration adds adversarial stand-ins (thin wall, micro-jitter with smooth normals, a one-view notch, texture transforms, a tiled texture rotated per instance), reports bootstrap or leave-one-out intervals for each threshold, and tessellation and texture-resolution sweeps; defaults change only where the evidence supports it, recorded in the calibration table.
5. **Equivalence:** proof assets and fixtures keep their verdicts or each change is justified in the delivery.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Each adversarial stand-in fails the rule it targets; honest scans still pass.

## Rules

- Follow `CONTRIBUTING.md`. CC0 data only for calibration, cached, never committed.
- **Allowed files:** `src/judge/natural*.ts`, `bridge/judge/judge_natural*.py`, `bridge/judge/judge_skeleton*.py` only if needed, `scripts/calibrate-natural.ts`, `scripts/lib/natural-*`, `schemas/**`, `test/judge/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs run one at a time; this one starts when the judge chain reaches it.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs `npm run calibrate:natural -- --verify` and the adversarial set, and sees each attack fail and each scan pass.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
