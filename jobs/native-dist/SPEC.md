# Job: Native dist — users get the fast core without installing Rust

The terrain core (`native/`) is Rust. Today a user without cargo gets the Python reference kernels, which are roughly a hundred times slower. Ship prebuilt cores, the way NumPy, Pillow and Polars ship compiled code, so that only contributors who change the core need Rust.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Prebuilt cores.**
   - A reproducible build of the core for Windows x64, Linux x64 (glibc 2.31 or older baseline), macOS arm64 and macOS x64.
   - It comes from a CI workflow (GitHub Actions matrix) with pinned toolchains, and it is offline-buildable from the vendored sources.
   - The workflow produces one artifact per platform and a manifest with each file's sha256 and the source commit.
2. **Packaging.**
   - The npm package and the Blender add-on zip carry the cores for every platform, or for the platform they are built for, as stated.
   - A missing platform is a clear build error in release mode.
3. **Loading.**
   - The loader picks the core for the running platform and architecture, checks its sha256 against the manifest, and records the result: loaded, missing or mismatched.
   - It refuses a mismatched file.
   - A locally built core, from cargo in a developer tree, takes precedence when present and is reported as such.
4. **Fallback.**
   - With no usable core, Blendworks still works on the Python reference.
   - The fallback states the reason and the expected slowdown once per session. It appears in `blender_scene_info` or in the status result, and in the terrain command results.
5. **Docs.**
   - User install: no Rust needed.
   - Contributor build: Rust needed.
   - How to cut a release with the cores.
   - The supported platforms table.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the loader picks the right file per platform string;
- a manifest mismatch is refused;
- a developer build takes precedence;
- the fallback reason and slowdown are reported;
- the packaging step fails in release mode when a platform is missing;
- the CI workflow file parses and names all four targets.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Workflow scope:** the CI workflow is added; it is not run by the judge. The judge checks it statically and through the packaging tests on local artifacts.
- **Allowed files:**
  - `.github/workflows/**`;
  - `scripts/**` for packaging and the native build;
  - the native loader module in `bridge/**`;
  - `package.json` scripts and `files`;
  - `docs/**`, `test/**`, `bridge/tests/**`.
- Do not change the kernels.
- **Environment and concurrency:** the machine is shared.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. On a machine where cargo is hidden from PATH, a packed npm tarball installed into a fresh directory loads the bundled Windows core (verified by sha256) and runs a terrain kernel at native speed.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
