# Job: Image repro — the judge image builds bit-identically again

`test/judge/container.test.ts` "builds the same digest again from the same commit, without any cache" fails on `main` since the native terrain core joined the judge image (terrain-kernels): two cache-free builds of one commit give different digests. A judge image that cannot be rebuilt identically cannot pin what was checked. Find every source of difference and remove it at the root.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Diagnose.**
   - Build the image twice without cache from one commit, and compare the layers file by file (a diffoscope-style comparison of the extracted layers).
   - List every differing file and its cause, for example: rustc or cargo output with embedded paths, timestamps or codegen-unit ordering; build ids; Python bytecode; npm or tsc output; file metadata.
2. **Fix at the root.**
   - The native build is deterministic: fixed paths with `--remap-path-prefix`, a fixed `SOURCE_DATE_EPOCH`, codegen settings that give stable output, and no build ids or timestamps.
   - The same holds for every other differing step.
   - No post-hoc normalisation of the image that hides a nondeterministic build.
3. **Guard.**
   - The existing digest test passes.
   - A faster test, without Docker, checks that two native builds of the same sources in different directories produce byte-identical libraries.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Allowed files:**
  - `docker/judge/**`;
  - `native/Cargo.toml` and `native/.cargo/**` (build settings only);
  - `scripts/**` where the build needs it;
  - `test/**`, `docs/**`.
- Do not change kernel code.
- **Environment and concurrency:** the machine is shared. Build at most one image at a time, and remove your images and build cache afterwards.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`, including `test/judge/container.test.ts`.
2. Every required item has a test that fails when its behaviour stops holding.
3. Two cache-free builds of the patched commit give the same digest.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
