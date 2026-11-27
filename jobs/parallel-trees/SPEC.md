# Job: Parallel trees — the same output at any thread count, and trees built in parallel

Two measured facts (F:/blendworks-kit/throughput/REPORT.md):
1. **Output depends on Blender's thread count.** A scene built at 32 threads and at 4 threads differs in the `EDGE:sharp_edge` attribute of every terrain tile, the lake, the river and every tree bark. Between 1 and 25 % of edges flip; coordinates and topology are identical. Hash proofs therefore only hold at equal thread counts, and the judge (4 CPUs) and a desktop disagree.
2. **Trees are about half of a landscape build and run on about one core.** Building them in two worker processes on 4 CPUs was 1.77× faster (65.9 → 37.2 s plus 2.4 s to merge) and bit-identical at equal thread counts.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Thread-independent output.**
   - Find the root cause of the thread-dependent `sharp_edge`. Candidates are `Mesh.set_sharp_from_angle` in `liquid_mesh.py` and `commands/liquid_fill.py`, and the sharp marking of heightfield tiles and tree bark.
   - Make every Blendworks command's geometry and attributes identical at any Blender thread count.
2. **Parallel tree builds.**
   - Add a batch command (for example `grow_trees`) that builds many trees in child Blender sessions, each writing its trees to a .blend, then appends them into the scene.
   - Collections are copied, and materials and images are deduplicated by content.
   - Names follow the same rules as building serially.
   - The number of workers comes from the CPUs and memory available, with a stated per-worker memory estimate. A failed worker falls back to building serially.
3. **Same result.** The parallel build plus merge equals the serial build: geometry hashes, names, collections and material node digests.

## Targets

On the judge's 4 CPUs, building trees runs at least 1.7× faster than serial for 6 or more trees. On the host with 4 workers, at least 2.5× faster.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the bench or check scene's geometry hashes, including `sharp_edge`, are identical at `-t 1`, `-t 4` and `-t 32`;
- parallel equals serial;
- a killed worker falls back to serial;
- the speed target holds on the check-size tree set.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes: identical output, and the fix goes in general code.
- **Allowed files:**
  - the sharp-edge sources named above and any other source you find;
  - the tree commands and a new worker-session module;
  - `blendfile.py` for appending;
  - `bench/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own outside the speed measurement.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the tree benchmark in the judge image. The targets hold, and the hashes are identical across thread counts.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
