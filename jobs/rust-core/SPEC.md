# Job: Rust core — compiled kernels for the grid algorithms that must run step by step

Terrain and water work in Blendworks is limited by algorithms that cannot be written as whole-array operations, because each step depends on the one before:
- droplet erosion;
- routing water downhill in order;
- filling depressions from the outlet inward;
- solving stream-power incision along the flow order;
- slope failure that cascades.

In Python these run 50 to 100 times slower than compiled code. The landforms work measured that a region big enough for its reference measures cannot be built within the judge's time.

Add a small compiled core in Rust for these kernels. Blender's Python calls it, and a Python reference gives the same results when the core is absent. The core builds from source on Windows and in the Linux judge image with no network access.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **The core:**
   - A Rust crate in the repository (for example `native/`) built as a C-ABI dynamic library with **no external crates**, so it builds offline.
   - It is loaded from Blender's Python with `ctypes`, which passes numpy buffers without copying.
   - The crate builds with the Rust version in Debian bookworm (1.63) and with current stable. State the minimum version and test it.
   - One build command (`npm run build:native`, also run by `npm run build`) builds it for the host.
   - The bridge finds it at a stated path. When it is missing, or fails to load, the bridge reports the cause once and uses the Python reference.
2. **The judge image:**
   - `docker/judge/Dockerfile` installs the Rust toolchain from the pinned Debian snapshot the image already uses, so the image stays reproducible.
   - The image builds the core during `npm run build`. Inside the image, the check runs with the core loaded and fails if it does not load.
3. **Kernels, each with a Python reference of the same algorithm in a new bridge module:**
   - flow directions on a grid: steepest descent (D8) and multiple flow with a slope exponent (Freeman 1991), with a stated rule for flats;
   - topological order of a flow graph, and flow accumulation along it;
   - depression filling or breaching: priority flood with epsilon (Barnes, Lehman & Mulla 2014), plus the depression and spill-point labels;
   - implicit stream-power incision along the flow order (Braun & Willett 2013), for n = 1 and for general n by Newton iteration;
   - threshold hillslope failure to a critical angle (cascading);
   - hydraulic droplet erosion and thermal talus, exactly as `erode` does them now.
4. **`erode` uses the core:**
   - The `erode` command's droplet and thermal loops call the core.
   - The results equal the current Python code: bit-identical heights for the same seed, or a stated tolerance where floating-point order must change, with the reason.
   - Its public behaviour does not change.
5. **Same results everywhere:**
   - Every kernel matches its Python reference on the same inputs: bit-identical for integer outputs such as directions, order and labels, and within a stated tolerance for floats.
   - The match is tested on random grids, flats, pits, nested depressions, borders and NaN or no-data cells.
   - Windows and Linux give the same results.
6. **Speed, measured:**
   - A benchmark under `bench/` times each kernel against its Python reference on grids of 257², 513² and 1025², in CPU time.
   - It records the results in `docs/research/rust-core.md`.
   - Target: each kernel at least 20 times faster than the Python reference at 513², and `erode` at least 10 times faster end to end.
7. **Safety:**
   - The core checks buffer sizes, shapes and types before touching memory, and returns errors instead of crashing.
   - No unsafe code outside a small, stated FFI layer.
   - Panics never cross the FFI boundary.
   - A fuzz-style test feeds wrong shapes, empty grids and extreme values.
8. **Docs:** how the core is built, loaded and tested; how to add a kernel with its Python reference; the measured speed table.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- each kernel equals its reference on the stated cases;
- `erode` heights equal the old code for stored seeds;
- the bridge falls back with a reason when the library is missing;
- the judge image refuses to pass when the core does not load;
- wrong buffers return errors and do not crash Blender;
- the speed guard fails when a kernel is made slower than a stated factor over its calibrated time.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Judge procedure:** because this job changes the judge image, the judge builds the image from `main` with the patch applied and runs the check in that image.
- No quick fixes: the same algorithm in both languages, no lowered quality or skipped work for speed, and no tolerances chosen after measuring.
- **Allowed files:**
  - the new crate directory;
  - new bridge modules for the kernels and the loader;
  - the loop internals of the `erode` command;
  - `docker/judge/**`, `scripts/**` where the build and the image need it, `package.json` scripts;
  - `bench/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default. The machine is shared with other jobs.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image built from `main` with the patch applied, with the core loaded.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the benchmark in that image. Every kernel meets its speed target, and `erode` gives the same heights as before.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
