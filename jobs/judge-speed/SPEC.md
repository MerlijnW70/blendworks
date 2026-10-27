# Job: One Blender process per judge run, and a fast UV pack

A full check takes about 6 minutes, and the floor is set by about 450 Blender process starts and a slow UV pack: `test_uv_coverage` alone takes about 120 s. The judge starts a separate Blender process for measuring and for rendering, so every judged asset pays the start and load cost several times. Make the judge measure and render in one Blender process, and make the coverage-aware UV pack fast, without changing a single verdict.

## Base

- **Base commit:** 3c16861. Rebase onto the latest `main` before delivering.

## Required

1. **Single-process judge:**
   - One judge run loads the delivered asset once, in one sandboxed Blender process, then measures, renders the contact sheet and close-ups, and makes the reference silhouettes.
   - Sandbox guarantees are unchanged: network, mount and PID namespaces, prlimit, the low-integrity token on Windows, and the private delivery copy.
   - A crash or timeout in any stage is still reported per stage, with the stage timings.
   - Stage isolation that matters for integrity is preserved. For example, a render must not be able to change a measurement; show how.
2. **Identical verdicts:** for all proof assets (torch, crate, rocks, drill rig, pickaxe, armillary, armillary-v2) and all judge fixtures, the report's rules, values and verdict are identical before and after, apart from timings.
   - Add an equivalence test or script that proves this.
3. **Fast UV pack:**
   - `uv_pack` with a coverage target reaches the same or better coverage, at the same texel-density constraints, at least 4x faster on the `test_uv_coverage` fixture and on the armillary-v2 parts.
   - Find where the time goes (profile it), and fix the search. Lowering the target or the iterations is not a fix.
3a. **Fewer process starts in tests:** reduce Blender process starts in the test suite by sharing one process per test file where the tests are independent. Report the start count before and after.
4. **Measured result:** report the wall time of a full `npm run check` before and after, and the judge time per proof asset before and after, on this machine, at `BLENDWORKS_JOBS=2`. The target is at least 2x faster for the judge and at least 35 % faster for the full check.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- An equivalence test of the verdict and values against the stored reports of the previous judge for the fixtures.
- A test that a render stage cannot change a measured value.
- A stage crash is reported for the right stage.
- UV pack coverage is at least as high as before, within a time bound, on the fixture.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:**
  - `src/judge/**`, `bridge/judge/**`;
  - `bridge/blendworks_bridge/commands/uv_pack.py`, `bridge/blendworks_bridge/uvlayout.py`, `bridge/blendworks_bridge/texel.py`;
  - `test/**` (test harness and fixtures; list the changed existing tests), `scripts/**`, `docs/**`, `package.json` scripts.
- **Files shared with other open jobs:** the modeling-3 job owns the rest of `bridge/blendworks_bridge/**` and `src/mcp/**`. The job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. The equivalence proof shows identical verdicts and values for every proof asset and fixture.
3. Every required item has a test that fails when its behaviour stops holding.
4. The judge re-runs the before and after timings on two proof assets and sees the reported speed-up.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
