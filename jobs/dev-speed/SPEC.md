# Job: A fast, safe check and a repo that is easy to start with

The full check takes about 2 minutes 20 on the judge's machine. Test fixtures are generated four times, bridge tests run strictly one after another, and nothing caps how many Blender processes run at once (the machine froze once under parallel load). Workers have no fast check to iterate with. The Blender path is hard-coded in four places, and the README is five lines. Fix all of this properly.

## Required

1. **Fixtures built once:**
   - A vitest `globalSetup` generates the judge fixtures once, into a cache folder keyed by the sha256 of the fixture scripts and the Blender version, under one ignored cache root (for example `.cache/`).
   - Concurrent runs are safe: generation is locked and atomic.
   - Every test file that called `makeFixtures` uses the cache.
2. **Global concurrency cap:**
   - One setting (`BLENDWORKS_JOBS`, default 2) limits concurrent Blender processes across vitest workers and the bridge-test runner.
   - It uses a cross-process lock or semaphore in the cache root, not per-process counting.
   - Blender is started with a thread cap where Blender supports one.
3. **Parallel bridge tests:**
   - `scripts/bridge-tests.mjs` runs files in a pool bounded by the cap.
   - It accepts file filters (`npm run test:bridge -- test_render`).
   - It reports the time per file and the slowest files.
4. **Two tiers:**
   - `npm run check:fast` is for iteration: rules, typecheck, unit tests that need no Blender, and the bridge or judge tests related to changed files, by a documented mapping.
   - `npm run check` stays the full gate, with the same coverage as today, and is faster.
   - Measure and report both times on the judge's machine, before and after. The aim is a full check clearly faster than 2:20 with `BLENDWORKS_JOBS=2`.
5. **One Blender path:**
   - A single module resolves Blender: the `BLENDER` variable, then a platform default list.
   - It gives a clear error with a download link, and checks the pinned version (5.2).
   - `src/blender.ts`, the scripts and `build-addon.mjs` use it.
   - Remove the machine-specific default `F:\tools\...` from code and docs; document it as an example only.
6. **`npm run doctor`:** checks Node, Blender path and version, GPU devices (`BLENDWORKS_DEVICE`), WSL sandbox tools (`unshare`, `prlimit`) where relevant, and the cache folder. It prints what is fine and what to fix.
7. **Clean runs:** tests write only under the cache root or the OS temp directory, never in tracked paths, and the cache can be cleared (`npm run clean`). Extend `.gitignore` (cache root, logs, `*.blend1`, coverage, `.sota/`).
8. **README quickstart**, at most two screens:
   - what Blendworks is (the MCP server, the judge and the add-on);
   - prerequisites, with a Blender link;
   - `npm ci`, `npm run doctor`, `npm run install-claude`;
   - an example prompt;
   - judging an asset with `blendworks judge`;
   - an environment-variable table (`BLENDER`, `BLENDWORKS_DEVICE`, `BLENDWORKS_JOBS`, `BLENDWORKS_PORT`, `BLENDWORKS_LIVE`, `BLENDWORKS_LIBRARY_MAX_MB`);
   - a platform table (Windows native, WSL or Linux: what is supported and which tests skip).
   Every command in it must be run and checked.
9. **Job template:** `jobs/TEMPLATE.md` covers:
   - base commit;
   - allowed files, plus "existing tests that assert changed behaviour may be updated, list them";
   - files shared with other open jobs;
   - environment and the concurrency rule;
   - `check:fast` for iteration and `check` once at the end;
   - one negative test per acceptance item;
   - generated fixtures, never committed binaries.
   Update `CONTRIBUTING.md` to point to it and to `check:fast`.

## Tests

- **Cache:** the cache key changes when a fixture script changes. Two concurrent setups generate once.
- **Concurrency cap:** with `BLENDWORKS_JOBS=1`, no two Blender processes overlap. Prove it with timestamps written by a probe.
- **Blender path:** resolution order and the error message, with a fake missing path.
- **Bridge filters:** the bridge-test runner's filter and pool.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only `package.json` (scripts), `package-lock.json`, `scripts/`, `vitest.config.ts`, `src/blender.ts`, `bridge/build-addon.mjs`, `bridge/build_addon.py`, test setup and helpers (`test/**/helpers.ts`, new setup files), `.gitignore`, `README.md`, `CONTRIBUTING.md`, `jobs/TEMPLATE.md` and the Blender-path paragraph of `docs/DESIGN.md`.
- You may update existing tests where they use the old fixture or Blender-path helpers. List them in your report.
- The judge-QA job may change judge fixtures and tests. The session-robustness and modeling-kit jobs change the bridge and the MCP. Rebase onto the latest `main` before delivering.
- Keep the PC usable while you work: respect your own cap.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when the concurrency cap stops holding, or when fixtures are regenerated on a cache hit.
3. The judge times `check` before and after on the judge's machine, runs `doctor`, and follows the README quickstart from a fresh clone.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Include the before and after timings. Announce its sha256 to the judge.
