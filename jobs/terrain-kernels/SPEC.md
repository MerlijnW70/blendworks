# Job: Terrain kernels — the compiled core for landscape evolution

The terrain research (the job workspace) found the best known way to mountains that pass for photographs. It is an uplift field cut by implicit stream power with lake routing and hillslope diffusion at 30–60 m, then multi-scale amplification to a few metres. The earlier landforms attempt spent 1.2–2.1 ms of CPU per cell. Published serial code needs about 0.25 µs per cell per step. Build the compiled kernels this engine stands on, so that the next jobs (fluvial core, glacial stage, amplification) can run 1–4 million cells within the judge's minutes.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.
- **Earlier work.** A cancelled job left a dependency-free Rust crate on branch `rust-core` in the job workspace: a ctypes loader, a Python fallback, a Dockerfile toolchain and nine kernels. Reuse what fits, and measure everything against this spec.

## Required

1. **The core.**
   - A Rust crate (no external crates; it builds offline with Debian bookworm's rustc 1.63 and with current stable) loaded from Blender's Python through `ctypes` on numpy buffers without copying.
   - It builds with `npm run build`.
   - The judge image builds it from the pinned Debian snapshot and the check requires it there.
   - On other machines a missing core falls back to the Python reference, with a single stated reason.
2. **Kernels.** Each kernel has a Python reference of the same algorithm in a new bridge module.
   - **Receivers:** D8 and multiple flow with exponent p, with flats resolved.
   - **Ordering:** a breadth-first receiver queue with levels (Barnes 2018), plus accumulation along it.
   - **Depressions:** lake routing by the basin graph and minimum spanning tree (Cordonnier, Bovy & Braun 2019), in filling and carving modes, with lake labels and spill points. Also Priority-Flood with ε (Barnes et al. 2014).
   - **Incision:** implicit stream-power incision (Braun & Willett 2013), for n = 1 and, by Newton iteration, for general n.
   - **Diffusion:** linear diffusion by ADI and non-linear critical-slope diffusion (Roering et al. 1999), both stable for long steps.
   - **Thermal slides:** a slope-limited mass transfer with a per-cell critical angle field.
3. **Threads with deterministic results.**
   - Kernels may use `std::thread` with a fixed partition.
   - Results are identical at every thread count and on Windows and Linux: bit-identical for integer outputs, and within a stated tolerance for floats where summation order must change, with the reason.
4. **Safety.**
   - Buffer shapes, types and sizes are checked before use.
   - Errors return; panics never cross the FFI boundary.
   - Unsafe code is confined to a small stated FFI layer.
   - A fuzz-style test feeds wrong shapes, empty grids, NaN and extreme values.
5. **Docs.**
   - How to build, load and add a kernel.
   - A speed table from the benchmark.

## Targets

Absolute CPU targets, measured by a benchmark under `bench/`:
- one implicit stream-power step (receivers, ordering, accumulation, incision) at most 0.5 µs per cell on one thread at 2049²;
- lake routing at most 1 µs per cell at 2049²;
- an ADI diffusion step at most 0.3 µs per cell;
- at 4 threads, each kernel at least 2.5× faster than at 1 thread, at 2049².

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- each kernel equals its reference on random grids, flats, nested depressions, borders and no-data;
- outputs are identical at 1, 2 and 4 threads;
- a stream-power run reaches steady state on an analytic uplift case with the known slope–area relation within a stated tolerance;
- the fallback works with a reason;
- bad buffers return errors;
- the speed guard fails when a kernel is slowed beyond a stated factor of its calibrated time.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Judge procedure:** this job changes the judge image, so the judge builds the image from `main` with the patch applied.
- No quick fixes: the same algorithm in both languages, exact or stated tolerances, no lowered work.
- Write the kernels from the papers. FastScapeLib (GPL-3.0) and Badlands (LGPL/GPL) may be read for understanding, but code must not be copied from them.
- **Allowed files:**
  - the crate directory;
  - new bridge modules for the kernels and the loader;
  - `docker/judge/**`;
  - `scripts/**` where the build needs it;
  - `package.json` scripts;
  - `bench/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image built from `main` with the patch.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the benchmark in that image, and the targets hold.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
