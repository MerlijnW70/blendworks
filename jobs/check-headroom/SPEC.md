# Job: Headroom for the slowest test and a judge that honours "retry"

`test/judge/equivalence.test.ts` judges every equivalence fixture in one file. In the judge image it works 340 to 450 s on a quiet host against the 600 s per-file work budget, and about 690 s when the host is busy, so the check fails on load alone (2 of 10 fresh-container runs in the check-startup proof). Every judge job adds fixtures, so the margin shrinks with each one. Separately, `npm run check` now exits 75 when a failure is environmental, but `src/judge/container/patch.ts` treats every non-zero exit of the check as a fail, so a paid judge can still reject good work for a machine fault.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Equivalence within budget by construction:** split the equivalence fixtures across files or shards whose work stays below half the per-file budget in the judge image on a quiet host, with the split derived from the measured cost per fixture (recorded, like `scripts/durations.json`) so that adding fixtures adds shards instead of growing one file. No fixture is dropped, no expectation is loosened, and the fixtures run in parallel within the check's process budget.
2. **Faster where it is waste:** profile the equivalence run and remove repeated work (for example Blender start-ups per fixture, re-imports, renders the rules do not use), with the before and after per-fixture cost reported.
3. **A guard:** the check fails with a clear message when any test file's recorded work in the image exceeds half the per-file budget, so the next slow file is caught before it flakes.
4. **Retry honoured:** `blendworks-judge patch` maps an exit 75 of the check to the judge's "retry later" outcome (no verdict) and every other non-zero exit to a fail, documented with the exit-code table in `docs/DESIGN.md`; a delivery cannot make its own failure exit 75 (state how: for example the decision is taken by the check's runner from the cgroup counters and resource errors, not by test code).

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: a fixture list whose cost exceeds one shard is split; the guard trips on a recorded slow file; exit 75 from the check gives no verdict and exit 1 gives a fail; a test that tries to exit 75 itself still fails.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image).
- **Allowed files:** `test/judge/equivalence*`, `scripts/lib/equivalence.ts`, `scripts/judge-equivalence.mjs`, `scripts/durations.json`, `scripts/lib/file-limits.ts`, `scripts/lib/checks.ts`, `src/judge/container/**`, `test/tooling/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs run one at a time; this one starts after judge-materials lands.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the check ten times in fresh containers on a quiet host and sees ten passes, with every test file below half its work budget.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
