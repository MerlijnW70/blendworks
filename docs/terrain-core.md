# Terrain core

The compiled kernels that landscape evolution stands on: flow receivers, the breadth-first receiver queue, accumulation, lake routing, Priority-Flood, implicit stream-power incision, hillslope diffusion and thermal slides. They live in the Rust crate `native/` (no external crates) and are called from Blender's Python through `ctypes` on numpy buffers, without copies. Every kernel has a Python reference of the same algorithm, and without the core the bridge runs the reference instead.

| Kernel | Export | Reference | Method |
|---|---|---|---|
| D8 receivers, flats resolved | `bw_d8` | `terrain_flow.d8` | steepest descent (O'Callaghan & Mark 1984); flats drained by Barnes, Lehman & Mulla 2014 |
| Multiple-flow receivers, exponent p | `bw_mfd` | `terrain_flow.mfd` | shares proportional to (drop / distance)^p (Freeman 1991); resolved flats send everything to their D8 receiver |
| Receiver queue with levels | `bw_order` | `terrain_order.order` | breadth-first queue from the outlets with levels (Barnes 2019); donor lists in a fixed order |
| Accumulation | `bw_accumulate` | `terrain_order.accumulate` | every cell pulls its donors' totals, level by level from the top |
| Lake routing, filling and carving | `bw_route_lakes` | `terrain_lakes.route` | basin graph and its minimum spanning tree (Cordonnier, Bovy & Braun 2019), built by Boruvka's algorithm; lake labels, water level and spill points |
| Priority-Flood+epsilon | `bw_priority_flood` | `terrain_flood.priority_flood` | Barnes, Lehman & Mulla 2014, Algorithms 2 and 3 |
| Implicit stream-power incision | `bw_incise` | `terrain_incision.incise` | Braun & Willett 2013; closed form for n = 1, bracketed Newton for any other n |
| Linear and non-linear diffusion | `bw_diffuse` | `terrain_diffusion.diffuse` | alternating-direction implicit in locally one-dimensional form; Roering, Kirchner & Dietrich 1999 by Picard iteration |
| Thermal slides | `bw_slide` | `terrain_thermal.slide` | slope-limited mass transfer with a critical tangent per cell |

The public entry points are in `bridge/blendworks_bridge/terrain_kernels.py`. Each takes `engine="auto"` (the core when it is loaded, else the reference), `"core"` or `"python"`, and `threads` (default: the CPU count, at most 4).

## Conventions

- **Grids** are row-major, `rows x columns`; rows grow along +y, columns along +x; `spacing` is `(dx, dy)` in metres. A cell whose height is not finite is no-data: it neither drains nor receives.
- **Base level** is set by `edges`, a bit mask: 1 north (row 0), 2 east, 4 south, 8 west, 16 no-data. A valid cell on an open side, or next to a no-data cell when bit 16 is set, is an outlet. Outlets have no receiver and keep their heights in incision, diffusion and slides.
- **Neighbours** are taken east first, then clockwise (east, south-east, south, south-west, west, north-west, north, north-east); ties go to the first.
- **Receiver tables** are int32, cell-major, `width` slots per cell (1 for D8, 8 for multiple flow), `-1` for none. A table must not name a cell itself or the same receiver twice; a cycle is reported as such.
- **Orders** hold every cell once; `level_start` holds the offsets of the levels in the order. Donor lists hold table entries `cell * width + slot` in a fixed order: neighbours in neighbour order, then farther donors (a filled pit's receiver may be a distant pass cell) by entry.
- **Lake routing** numbers the basins: 0 is every basin that drains to an outlet (the sea), pits are 1, 2, ... in ascending cell order. `lake` labels a flooded cell with the basin whose own pass sets the water level; `spill[b]` and `spill_to[b]` are the pass cells of basin `b` on its side and across. Basins no path joins to an outlet are rooted at their lowest pit, which stays a pit. Each cell takes its basin from the root its receivers lead to (walks in row order in the core, pointer jumping in the reference), so lake routing does not read the order it is given beyond checking its size, and a receiver cycle is an error.

## Threads and determinism

Kernels use `std::thread::scope` with a fixed partition: contiguous spans of rows, cells or the cells of a level, whose bounds depend only on the length and the thread count. Each output value is computed by one thread with the same operations in the same order whatever span it falls in, and each sum (accumulation, Thomas sweeps, slides) runs in one fixed order. Values a thread writes and another reads after a barrier are relaxed atomics, which compile to plain loads and stores. So every output, integer and float, is bit-identical at every thread count; no summation order changes, so the float tolerance is zero. Powers come from `native/src/pow.rs` (and `terrain_pow.py`), built from additions, multiplications, divisions and square roots only, because the system `pow` differs in its last bit between C libraries; with it the floats are bit-identical on Windows and Linux too. `test_terrain_threads.py` checks 1, 2, 4 and 7 threads and compares digests recorded on Windows with the run in the Linux judge image. Priority-Flood is one sequence of queue pops and runs on one thread.

## Safety

- `native/src/ffi/` is the only code with `unsafe` (`lib.rs` denies it everywhere else): `mod.rs` checks every buffer descriptor (element type, length, C-contiguity, alignment, writability, overlap with the other buffers of the call, null pointers) before it makes a slice, and `views.rs` lends output buffers to the threads as atomics.
- Every export runs inside `catch_unwind` and returns 0, 1 (invalid argument), 2 (flow graph cycle) or 3 (internal error); `bw_last_error` copies the message. A panic in a worker thread poisons the barrier, so the other threads stop instead of waiting, and the call returns 3.
- Kernels check lengths against the grid, receivers against the cell range, orders for being permutations, and settings for range before they run.

## Build

`npm run build` runs `scripts/build-native.mjs` (cargo `build --release --offline --locked` into `native/target`) before the TypeScript build; `npm run build:native` runs it alone, and `npm run test:bridge` runs it before the bridge tests. The crate needs Rust 1.63 or newer, the rustc of Debian bookworm, and nothing else. The judge image installs rustc and cargo from the pinned Debian snapshot, checks the version and writes `/etc/blendworks/native-required`; there, and wherever `BLENDWORKS_NATIVE=require` is set, a missing toolchain or a core that does not load is an error. Elsewhere a missing cargo only means the bridge uses the Python references; a crate that fails to compile is always an error.

## Load

`terrain_core.core()` loads the file `BLENDWORKS_NATIVE_LIB` names, else `native/target/release/<library>`, else the sha256-checked prebuilt core bundled for the platform (see `native-cores.md`), once per process; on Windows it loads a copy named by the file's hash, so a rebuild never meets a locked file. If the library is missing, does not load or has another ABI version, it prints one line, `blendworks: <reason>; using the Python reference kernels`, and `terrain_kernels` runs the references, unless the core is required. `terrain_core.status()` reports what happened.

## Add a kernel

1. Write the kernel in its own module under `native/src/` as safe Rust on slices: check lengths and settings, return `KernelResult`, split work with `team::rows_mut`, `team::spans` or `levels::Levels::sweep`, and keep every output value's operations independent of the span it lands in.
2. Export it in `native/src/ffi/entries.rs`: read the grid with `grid_of` and each buffer with `Buffers`, and run the kernel inside `guarded`. Raise `ABI_VERSION` in `ffi/mod.rs` and `terrain_core.py` when a signature changes.
3. Add its signature to `SIGNATURES` in `terrain_core.py`, write the reference in a `terrain_<name>.py` module with the same operations in the same order, and dispatch both in `terrain_kernels.py`.
4. Add it to the cases of `test_terrain_kernels.py` (reference equality), `test_terrain_threads.py` (thread counts and recorded digests), `test_terrain_safety.py` and, when it is timed, to `terrain_speed.py` and the benchmark; record the calibration with `bench/terrain-kernels/calibrate.py` and the table with `npm run bench:terrain -- --record`.

## Speed

`npm run bench:terrain` builds a 2049 x 2049 terrain (a stream-power landscape grown at 257 x 257, upsampled, with noise of 2e-4 of its relief, so lake routing has many pits; base level on the south edge), times every kernel at 1 and 4 threads (fastest of three runs) and fails when a target misses: one stream-power step (D8 receivers, ordering, accumulation, incision on the lake-routed graph) at most 0.5 µs per cell on one thread, lake routing at most 1 µs, an ADI step at most 0.3 µs, and every threaded kernel at least 2.5 times faster on 4 threads. Accumulation, ADI diffusion and non-linear diffusion (ADI sweeps inside each Picard iteration) are stated exceptions to the speedup rule; see below. The stream-power step is a sum of kernels, each judged on its own row. `--record` writes the table below. `test_terrain_speed.py` guards against regressions: each kernel's time over a calibration workload, both measured back to back, must stay within 4 times the ratio in `bench/terrain-kernels/speed-calibration.json`. Host noise of ±50 % on either side moves a ratio by at most 1.5 / 0.5 = 3 times, so it cannot trip the guard; accumulation run ten times over measured 7.3 times its calibrated ratio and failed it.

The table was measured in the judge image with `docker run --cpus 4` on a shared 32-thread host (the CPU count shown is the host's), with the host's load between 48 % and 93 %. On that host the 4-thread ratios of the same code swing by about ±0.4 between runs: incision with Newton and ordering for multiple flow fell just below 2.5 here and measured above it in other runs (multiple-flow ordering 3.1–3.5 times on Windows).

### Memory-bound exceptions

Accumulation and the diffusions do a few loads and stores per cell and almost no arithmetic, so at 4 threads they wait on memory, not on the threads:

- **The memory ceiling.** On the judge host an independent random gather over the same 2049² order (three loads per cell, no barrier and no dependency between cells) reaches only 3.35 times at 4 threads; streaming bandwidth does not grow past one thread (31.8 against 33.3 GB/s). Accumulation follows chains of dependent misses (donor offsets, then donors, then their totals) and writes at random, so it stays below that ceiling. Measured under a host load of 40–90 %: accumulation 2.09–2.27 times, ADI 1.98–2.53 times, at 0.018–0.023 and 0.019–0.022 µs per cell on one thread.
- **Barriers are not the limit.** A version that let each thread follow whole subtrees level after level without synchronising, splitting afresh only when the threads' shares drifted apart, was bit-identical and cut the barriers of accumulation from 6330 to 528; between 13 and 528 barriers it ran no faster than the level sweep (2.19 against 2.15 times, measured interleaved), so it was not kept.
- **Splitting by outlet trees cannot help.** After lake routing one outlet tree holds 73 % of the cells (3.08 of 4.2 million), so giving each thread whole trees caps the speedup at about 1 / 0.73 = 1.36 times. The basin tree of lake routing has the same shape: one subtree of the sea holds 140 thousand of the 180 thousand basins.

The single-thread times of these kernels beat their targets by 4 to 40 times, which is what the larger landscape jobs depend on.

<!-- speed table -->
2049 x 2049 cells, Linux-6.18.58.1-microsoft-standard-WSL2-x86_64-with-glibc2.36, 32 CPUs, fastest of 3 runs; the terrain has 302092 pits for lake routing and 5536 levels after it.

| kernel | µs per cell, 1 thread | µs per cell, 4 threads | speedup | target | holds |
|---|---|---|---|---|---|
| receivers (D8) | 0.0401 | 0.0097 | 4.13 x | speedup >= 2.5 | yes |
| ordering (queue with levels) | 0.0528 | 0.0208 | 2.54 x | speedup >= 2.5 | yes |
| accumulation | 0.0332 | 0.0122 | 2.71 x | memory-bound, speedup stated | yes |
| incision n = 1 | 0.1172 | 0.0269 | 4.35 x | speedup >= 2.5 | yes |
| lake routing | 0.1168 | 0.0417 | 2.80 x | <= 1 µs, speedup >= 2.5 | yes |
| ADI diffusion | 0.0351 | 0.0123 | 2.85 x | <= 0.3 µs, memory-bound, speedup stated | yes |
| non-linear diffusion (3 Picard) | 0.1938 | 0.0505 | 3.84 x | memory-bound, speedup stated | yes |
| thermal slides (1 iteration) | 0.0428 | 0.0153 | 2.80 x | speedup >= 2.5 | yes |
| incision n = 1.5 (Newton) | 0.1095 | 0.0439 | 2.50 x | speedup >= 2.5 | no |
| receivers (multiple flow) | 0.2462 | 0.0732 | 3.36 x | speedup >= 2.5 | yes |
| ordering (multiple flow) | 0.5209 | 0.2599 | 2.00 x | speedup >= 2.5 | no |
| accumulation (multiple flow) | 0.2781 | 0.0671 | 4.15 x | speedup >= 2.5 | yes |
| Priority-Flood+epsilon | 0.4122 | - | - | one thread | yes |
| stream-power step | 0.2433 | 0.0697 | 3.49 x | <= 0.5 µs, speedup judged per kernel | yes |
<!-- end speed table -->
