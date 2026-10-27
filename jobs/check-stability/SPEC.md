# Job: A full check that is fast and never fails because of load

`npm run check` now takes about six minutes on the judge's machine. When other work runs at the same time, it fails with 120-second timeouts in Blender-heavy judge tests: `judge/textures`, `judge/validator`, `judge/fixtures` and `mcp-polish-2`. This happens on a clean `main` too. The tests pass when run alone. A gate that fails for reasons unrelated to the code is not a gate. Find the root causes, make the check reliably green under load, and make it substantially faster.

## Base

- **Base commit:** `9e5310c`. Rebase onto the latest `main` before delivering.

## Required

1. **Diagnose first:**
   - Measure where time goes in the full check: per stage, per test file, per Blender process, including the time each process waits for a slot.
   - Prove why tests time out under load. Likely suspects:
     - slot waits counting against per-test timeouts;
     - `test:bridge` running concurrently with vitest and competing for the same slots;
     - judge renders using full samples and resolution in tests;
     - fixtures rebuilt per file.
   - Report what you find, with numbers.
2. **No timeouts from waiting:**
   - Per-test and per-hook timeouts measure only work, never time spent waiting for a Blender slot or for another stage. For example, start the timer after the slot is acquired, or give waiting its own bound.
   - A test fails on a real hang, never on queueing. Prove this with a test.
3. **Faster:**
   - Cut the full check to at most half its current wall time on the judge's machine at `BLENDWORKS_JOBS=2`, without dropping coverage. Ways to get there:
     - a documented test render profile (lower resolution and samples, set by an environment variable that only tests use, so production renders are unchanged), with assertions that are independent of resolution;
     - reusing judge fixtures and measurements across tests where they are read-only;
     - scheduling heavy files first, with sensible stage ordering;
     - removing duplicated work.
   - The judge's real defaults must stay exactly as they are. A test proves that production settings are unaffected.
4. **Stable under load:**
   - Add `npm run check:stress`. It runs the full check while a configurable CPU and Blender load runs beside it, for example a background loop of renders.
   - Document the result.
   - Acceptance: 3 consecutive full checks under that load, all green.
5. **Reporting:**
   - The check prints the slowest files and their slot-wait time.
   - On a timeout it names the stage and the test and says whether the time was spent waiting or working.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:** test setup and helpers (`test/setup/**`, `test/**/helpers.ts`, `test/tooling/**`), `scripts/**`, `vitest.config.ts`, `package.json` (scripts), and existing tests where you change only their timing, fixtures or render profile (list them). Production code changes are limited to reading the test render profile at a single documented entry point.
- **Files shared with other open jobs:** none. The open asset job touches no repo files.
- **Environment:** set `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe`.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when queueing time starts counting against a test timeout, or when the test render profile leaks into production renders.
3. The judge measures the full check before and after on the same machine, and runs `check:stress` to see it stay green.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Include the before and after measurements. Announce its sha256 to the judge.
