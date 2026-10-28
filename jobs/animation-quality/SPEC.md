# Job: Judge rules for animation quality and skin weights

The judge checks that clips exist, loop, stay in bounds and limit root motion, and that skins have at most four influences, normalised weights and a rest pose. It does not see whether an animation is physically believable or whether skinning deforms cleanly: feet that slide during contact, feet that sink into or float above the ground, jittery motion, joints bent past their limits, a loop that pops in velocity rather than position, or a joint that collapses volume when bent. Motion research measures these routinely (for example NVIDIA Kimodo's foot skate ratio and contact consistency, GMD-style skating, float and penetration, jerk). Add them as measured rules.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`motion` spec group,** measured on the delivered asset's clips at their own frame rate, in metres and seconds, per clip and reported per foot or joint:
   - `footSkate`: share of contact frames (foot point below a height threshold) whose horizontal foot speed exceeds a threshold (defaults after Kimodo: 0.05 m and 0.2 m/s; foot points found by bone map or declared in the spec);
   - `groundPenetration` and `float`: deepest foot point below the ground plane, and highest foot point above it during contact;
   - `jerk`: a percentile of the third finite difference of joint positions times fps³, normalised by character height;
   - `jointLimits`: per bone, the largest rotation outside declared or template limits;
   - `loopVelocity`: for looping clips, the velocity discontinuity at the wrap, in addition to the existing position check;
   - `selfPenetration`: share of frames where skinned surface parts intersect beyond a tolerance, on a sampled frame set.
   Defaults come from cited definitions where they exist; where they do not, from calibration on the Blendworks character examples and on deliberately broken versions, stated as such.
2. **`skin` additions:** `volumeRatio` under a stress pose set (each major joint bent to a stated angle): the ratio of deformed to rest volume of the skinned mesh per region stays within a band; `weightSmoothness`: no vertex whose dominant bone differs from all its neighbours' (stray weights); `symmetry` for mirrored rigs.
3. Each rule: values in the report and in `blendworks diff`, `null` fails, documented with its formula and source.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Fixtures (built by a fixture script with the rig commands on `main`): a clean walk, a walk with a sliding stance foot, a walk lowered into the floor, a jittery idle, an elbow bent backwards, a loop with a velocity pop, a mesh with stray weights, and a knee that collapses when bent; each fails only its own rule.

## Rules

- Follow `CONTRIBUTING.md`. No motion datasets with non-commercial terms in tests or calibration.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `schemas/**`, `test/judge/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs run one at a time; this one starts after judge-materials lands.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge judges the characters example's hero, fox and chest with the new groups and sees them pass, and each broken fixture fail only its own rule.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
