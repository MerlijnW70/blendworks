# Job: The check passes on Linux and inside the judge container

Paid code jobs will be judged inside the Blendworks judge image (Linux) through Solive's Docker sandbox. On Linux, `npm run check` fails at `main` today: `test/tooling/blender-path.test.ts` expects Windows path separators, `test/tooling/process-slots.test.ts` "two callers one slot" fails, `test/judge/equivalence.test.ts` compares against reports stored from Windows Blender, and the bridge tests `test_engrave_overlap.py` and `test_uv_coverage.py` give different numbers on Linux. Make the check pass on Windows, on Linux (WSL) and inside the judge container, without weakening any test.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Platform-correct tests:** path tests use the platform's rules (or test both explicitly); the slot test's failure on Linux is root-caused and fixed in the code or the test, whichever is wrong.
2. **Cross-platform equivalence:** find why stored judge reports differ between Windows and Linux Blender (float formatting, triangulation order, image decoding, thread counts, locale) and remove the difference at its source where possible; where a value genuinely differs by platform within float noise, the comparison uses a stated, justified tolerance per field rather than per-platform baselines.
3. **Bridge numbers:** root-cause the `test_engrave_overlap.py` and `test_uv_coverage.py` differences (for example non-deterministic iteration order, float32 accumulation, a platform-dependent library call) and make the code deterministic across platforms.
4. **CI-style proof:** a script that runs the full check inside the judge image (`patch` entry point) on the current commit, documented; the judge container's `patch` entry point passes a past code delivery.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. No wall-clock bounds; no weakened assertions (list every changed test and why it is not weaker).

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** the failing tests and the code they exercise, `scripts/**` (a container check runner), `test/**`, `bridge/tests/**`, the bridge modules behind the two numeric differences, `docs/**`. Do not change judge rules or verdict logic; only make the judge's values platform-independent.
- **Files shared with other open jobs:** judge jobs own `src/judge/**` and `bridge/judge/**`; coordinate by keeping changes there to value formatting or determinism fixes, listed separately in the delivery.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` on Windows; `~/tools/blender/blender` in WSL (distro `solive`, user `dev`); Docker Desktop for the image. At most `BLENDWORKS_JOBS` Blender processes at once.
- **While working:** iterate with single test files on both platforms. Run the full check once on Windows, once in WSL, and once in the container at the end, at low priority.

## Acceptance

1. `npm run check` passes on Windows, in WSL and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the container `patch` entry point on this delivery and on one earlier code delivery and sees both pass.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
