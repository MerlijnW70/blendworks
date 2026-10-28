# Job: Natural judge rules, part two: repetition, copies, branching and size laws

The natural group of the judge (`docs/DESIGN.md`, "Natural assets") measures silhouette dimension, solidity, surface roughness and albedo variation, calibrated on CC0 scans. It cannot yet catch the clearest signs of fake natural content: visible tiling, copy-pasted instances, branches that do not thin by a law, and sets whose sizes are all alike. Build the second half of plan item P11 (job B, section 5 of `docs/research/natural-shapes.md`), measured inside the existing one-process judge and its sandbox.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`natural.repetition`:** the highest normalised autocorrelation of each view's luminance away from zero shift (zero-padded, at least 25 % overlap, more than 16 px from zero), on the contact-sheet views the judge already renders; the rule takes `max` (research starting value 0.8), reports the worst view and its peak shift.
2. **`natural.instanceRepetition`:** the largest share of placed instances (glTF node instances and realized duplicate meshes, detected by mesh hash and transform) that share mesh, scale (within 1 %) and rotation about up (within 5°); `max` (starting value 0.1).
3. **`natural.leonardo`:** reads the skeleton from glTF `extras` (`blendworks.skeleton`, version 1; refuse other versions); per branching node solves `d^Δ = Σ d_i^Δ` for Δ from the radii measured on the mesh around the skeleton nodes (rays in the node's normal plane), and checks the median Δ within `[min, max]` (default `[1.8, 2.3]`, Eloy [S53]); without a skeleton the rule reports `null` and fails.
4. **`natural.sizeDistribution`:** the fitted power-law exponent (maximum likelihood, with the fitted minimum stated) of the instance or object size counts, by bounding-sphere diameter or, for trees, trunk diameter; checks `exponent` within `[min, max]`.
5. **Calibration:** extend `npm run calibrate:natural` with the measures that a CC0 scan set can calibrate (repetition on the scans' renders and texture images; size distribution on multi-object scan sets), report separation per rule as before, and only make a measure a default where it separates. Instance repetition and Leonardo take their defaults from the cited sources, stated as such.
6. Each rule follows the existing pattern: values in the report and in `blendworks diff`, `null` fails, the one-process judge keeps its single pass and stage isolation, and `docs/DESIGN.md` documents each measure, default and source. The natural spec templates gain the rules where they apply.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Repetition: an exactly tiled texture gives 1.0 within rounding; a Poisson-disk splat stays under 0.2; a jittered grid lies between, as measured in section 2.7.
- Instance repetition: 100 identical copies give 1.0; copies with random scale and yaw give a share under 0.05; realized duplicates are detected like instances.
- Leonardo: a synthetic skeleton and mesh built with `Δ = 2` gives a median of 2 within 0.05; with `Δ = 3` it gives 3; a tree of equal-radius cylinders fails; a missing skeleton reports `null` and fails.
- Size distribution: 2,000 sizes drawn from a power law with exponent −2 fit within ±0.15; uniform sizes fail a `[-2.5, -1.5]` band.
- Each rule passes and fails generated fixtures through the full judge; the equivalence fixtures gain the new fixture set without changing existing entries.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. CC0 data only for calibration, cached, never committed.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `schemas/**`, `scripts/**`, `test/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`, `package.json` scripts.
- **Files shared with other open jobs:** tree-mesh and lsystem own the bridge tree and plant modules and `src/mcp/**`; do not touch them.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge judges the scatter, phyllotaxis and tree examples on `main` with natural specs using the new rules, and sees the scores match what the renders show (no tiling in the scatter, Fibonacci order not flagged as copy-paste where scale and rotation vary, Leonardo's Δ near the skeleton's exponent).

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
