# Job: A check that reports progress as it runs

Paid code jobs are judged inside the judge image, where `blendworks-judge patch` stops `npm run check` when it prints nothing for 900 s, so a hung test becomes a fail rather than a judge timeout. But the check prints each phase's results only when the phase ends: the bridge test phase alone takes about 12 minutes on the image's 4 CPUs, so a slightly longer, healthy phase trips the quiet limit and fails good work (seen on a delivery that added rendering tests). The quiet limit must measure hangs, not long phases.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Streaming progress:** while phases run in parallel, the check prints a line as each test file finishes (phase, file, result, time) and a heartbeat line at a fixed interval naming the files still running, without interleaving partial lines; the final per-phase summaries stay as they are.
2. **Per-file limits:** a single test file that runs past a stated limit (configurable, default well under the 900 s quiet limit) is stopped and reported as a failure naming the file, so a hang inside one file fails fast and clearly instead of waiting for the judge's limit; the limit is documented and does not apply to files listed with a stated reason.
3. **Container proof:** in the judge image, the check of current `main` passes and never stays quiet for more than the heartbeat interval; report the longest gap.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. No wall-clock bounds in assertions (use injected clocks or event order).

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** `scripts/**`, `test/tooling/**`, `test/setup/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`; Docker Desktop for the image. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with single test files. Run the full check once on Windows and once in the judge image at the end.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the check in the image and sees a progress line at least every heartbeat interval.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
