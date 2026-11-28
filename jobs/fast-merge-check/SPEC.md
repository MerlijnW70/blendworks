# Job: Fast merge check — test what a change touches, keep the full check running behind

Every change runs all of the check: about 280 test files and about 700 Blender processes, 20 minutes on Windows and 28 in the judge, even when it touches three files. Blender starts again for nearly every test-side call, at 1.2–1.6 s each, which is 26–35 % of all Blender work (the job workspace). Development waits on this.

Make merging fast and keep full coverage:
- a selective check that runs exactly the tests a change can affect;
- a full check that keeps running on `main` behind it;
- warm Blender processes for test-side calls.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; `check-throughput` lands before this job, so build on its slots, memory gate and shared bridge runner.

## Required

1. **Affected-test selection.**
   - `npm run check:affected [--base <ref>]` derives the changed files from git.
   - It maps them to the test files that can be affected:
     - Python bridge modules: through the import graph of the bridge and its tests.
     - TypeScript: through the import graph of the sources and the vitest files.
     - Example scripts and docs: through their tests.
   - It runs those tests plus a stated core set (smoke and contract tests).
   - Changes to shared infrastructure select everything: the harness, the runner, limits, schema, handler, package files, Docker files, and anything the map cannot place.
   - The selection and its reasons are printed.
2. **Proof the selection is safe.**
   - A mutation study over at least 30 bridge and source modules, spread across the codebase: break each module once and run the full suite.
   - Every test that fails must be in the selection for that change.
   - The study is a script in the repository. A small version of it runs in `npm run check`.
3. **Full check behind `main`.**
   - `npm run check:watch` runs the full check on each new `main` commit in the background, at low priority with the host's slot limit.
   - It writes a result file and a short status line per commit (pass, or the failing files and their tail).
   - It never blocks or modifies the repository.
4. **Warm Blender for test-side calls.**
   - Calls that tests make to run a Blender script and read its result go to a small pool of long-lived Blender processes, one per slot, with a full factory reset and the leak fingerprint from `check-throughput` between calls.
   - Calls that need a fresh process opt out, with a reason: the judge's sandboxed runs, peak-memory assertions, startup tests.
   - The results of every test are the same as with fresh processes.

## Targets

- On Windows: `check:affected` for a typical single-module change takes at most 5 minutes. Measure five real past changes, for example the last five delivered patches, and report each time.
- The full check with the warm pool is at least 20 % faster than without it, at the same slots.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- a change to a module selects its tests and not unrelated ones;
- a change to shared infrastructure selects everything;
- the mutation-study sample proves every failing test was selected;
- the watcher writes a pass and a fail status for a fixture repository;
- the pool gives the same pass list as fresh processes, and a deliberate leak between calls is caught.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes:
  - no test skipped from the full check;
  - no per-file limit lowered;
  - the selection may err only on the side of running more.
- **Allowed files:** `scripts/**`, `src/blender.ts` and the test-side Blender call helpers, the bridge test harness, `package.json` scripts, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs:
   - `check:affected` on three recent patches, each within the target and selecting every test that the full suite shows failing under a planted bug in the changed module;
   - the full check with the pool, within the 20 % target.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
