# Job: Packed digest — images with packed files no longer crash parallel builds

Rendering `docs/examples/liquid_lake.py` from `main` (1a17fe4) on Windows fails inside `woodland` with `AttributeError: 'ImagePackedFile' object has no attribute 'data'`.

`blendfile.image_digest` iterates `image.packed_files`, which in Blender 5.2 yields `ImagePackedFile` items. Their bytes are on `.packed_file.data`, not `.data`. No test runs this path with a packed image, so it reached `main`.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Fix the digest.** Every packed image, single or multi-file (tiles, views), digests its packed bytes correctly through the Blender 5.2 API.
2. **Audit the same mistake.** Check every other use of packed files in the bridge, for example `exporting.py`, against the 5.2 API, and fix any wrong ones.
3. **Cover it.** Bridge tests build images with one packed file and with several (UDIM tiles), then run them through `image_digest` and through the parallel woodland and tree path that hit the crash. The tests fail on the old code.
4. **End to end.** The lake example renders on Windows from `main` with the patch.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Allowed files:** `bridge/blendworks_bridge/blendfile.py`, `bridge/blendworks_bridge/exporting.py`, other bridge modules only where the same packed-file mistake appears, `bridge/tests/**`, `test/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. `liquid_lake.py` completes and writes its shots.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
