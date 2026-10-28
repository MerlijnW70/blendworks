# Job: Faster, steadier checks

A full `npm run check` takes 9 to 14 minutes and several tests fail only under load. An infrastructure audit found the causes: every bridge edit regenerates all nine fixture sets although only one imports the bridge, and the cache key misses files one set does import; `check:fast` maps 33 bridge modules to the four smoke tests instead of their own tests; the check runs its phases serially; a quarter of the test files have no duration entry; Windows pid reuse can keep a dead slot lock forever; and five tests assert wall-clock bounds that CPU contention breaks. Fix each at its root, without weakening what any test checks.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Fixture dependencies:** each fixture script declares what it depends on (for example a `# fixture-deps:` header, or an import trace), and its cache key hashes exactly those files plus the Blender version: the whole `bridge/blendworks_bridge` tree only for scripts that import it, and `bridge/judge/*.py` files a script imports (such as `judge_font.py`). A test fails when a fixture script imports a bridge or judge module that its key does not cover. A cache hit refreshes the entry's age, and pruning never removes an entry that is locked or in use.
2. **`check:fast` mapping:** a bridge module `…/stem.py` selects `bridge/tests/test_<stem>*.py` by convention, the existing table stays as an override, bridge and `src` areas map to their `test/*-example.test.ts` files, and a test fails when a module has neither a table entry nor a convention hit nor a claiming test.
3. **Phases:** rules, typecheck and build run alongside the test phases with fail-fast, unless a test truly needs the build output (verify and state which).
4. **Durations:** the duration baseline covers every test file; `check` on a clean `main` refreshes it, or a test fails when a file has no entry.
5. **Locks:** slot and file locks record a start time or heartbeat, so a lock whose holder died is reclaimed even when Windows reuses its pid; slot waiting stops reading every slot file every 40 ms (back off or watch).
6. **Load-independent tests:**
   - `test/tooling/fair-queue.test.ts` and `test/setup/queue-probe.ts`: order by a barrier (a ticket file appearing in the queue), not by wall-clock offsets.
   - `test/judge/shared-access.test.ts`: the holder reports its own release time, and the assertions compare against it; no tight upper bounds.
   - `test/tooling/work-clock.test.ts`: an injected fake clock.
   - `test/uv/uv-pack.test.ts`: no absolute wall-clock bound; the deterministic pack-count proxy or an old-versus-new ratio measured in one probe.
   - A lint or test that refuses new `toBeLessThan(<milliseconds>)` wall-clock bounds outside an allow-list, plus a `waitFor(condition)` helper for new tests.
   The 20 ms routing-query test in `test/mcp-routing-bench.test.ts` is out of scope for this job (another job owns that file).
7. **Measured result:** report full-check wall time before and after on this machine at `BLENDWORKS_JOBS=2`, and the check time after a one-line bridge edit before and after (the fixture case). Run `npm run check:stress` 3 of 3 green.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

## Rules

- Follow `CONTRIBUTING.md`. No test may lose coverage or strength; list every changed existing test and why it is not weaker.
- **Allowed files:** `scripts/**` except `scripts/calibrate-natural.ts` and `scripts/lib/natural-*`, `test/setup/**`, `test/tooling/**`, `test/judge/shared-access.test.ts`, `test/uv/uv-pack.test.ts`, header lines of `test/judge/*fixtures.py`, `package.json` scripts, `docs/**` (CONTRIBUTING notes on writing load-independent tests).
- **Files shared with other open jobs:** natural-rules-b owns `src/judge/**`, `bridge/judge/**`, `schemas/**`, `scripts/calibrate-natural.ts`, `scripts/lib/natural-*`; tree-mesh owns the tree modules and `src/mcp/**`. The job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, and `npm run check:stress` passes 3 of 3 on a fresh clone.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge reproduces the before and after timings and the one-line-edit case.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
