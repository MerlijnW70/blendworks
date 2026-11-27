# Job: Scene speed — the tools a landscape uses, measured and made fast

A landscape scene calls the same heavy tools again and again: `scatter`, `ground_cover`, `grow_tree`, `tree_mesh`, `tree_leaves`, `liquid_body`, `material_layer`, `weather`, `atmosphere` and `render_final`. Nobody has measured where their time goes. Many inner loops walk vertices, points or particles in Python one at a time. Profile them, make them fast in general code with the same results, and keep them fast with a benchmark.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **A benchmark scene:**
   - A script under `bench/` builds a standard landscape with the tools above and records time per call. The landscape: terrain tiles, a lake and a river, 30 trees of three species, ground cover for two cameras, rocks, weather, haze, and a 1920×1080 `render_final`.
   - It also records peak memory and the output measures that prove the result is unchanged: vertex and instance counts, hashes of the generated geometry, and image statistics.
   - It runs on the CPU in the judge image. A smaller "check" size runs inside `npm run check`.
2. **Profiles:**
   - Profile each tool by function, with a cumulative-time table, and commit it under `docs/research/scene-speed.md`.
   - Name the hot paths, and give the before and after time for each.
3. **Fast in general code:**
   - Rewrite the hot paths with array operations (numpy, Blender's `foreach_get` and `foreach_set`, BVH and KD-tree queries, geometry nodes) instead of per-element Python loops.
   - Reuse structures across calls instead of rebuilding them. Avoid needless depsgraph updates.
   - Choose render settings that cost less noise per second, each with a stated reason and a measured noise-per-time result:
     - adaptive sampling;
     - light tree;
     - persistent data;
     - denoise prefilter;
     - texture limits and simplify for far instances.
   - **Target:** the benchmark scene builds at least 5 times faster in total on the judge CPU. Every tool that took over 5 s takes at least 3 times less.
4. **Same results:**
   - Every optimisation keeps its output.
   - Geometry hashes and counts must be identical. Where floating-point order changes, use a stated tolerance.
   - Images must match within a stated tolerance at equal settings.
   - Seeds give the same scene as before.
5. **Kept fast:**
   - The check-size benchmark runs in `npm run check`.
   - It fails when a tool gets slower than a stated factor over its recorded CPU time, scaled by a calibration run on the same machine so that hardware does not matter.
6. **Docs and MCP:**
   - The research note.
   - A "fast scenes" section on what costs what. Agents need it to plan budgets.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the benchmark records every call;
- outputs match the stored hashes and counts;
- a deliberately slowed function trips the speed guard;
- the render-settings change keeps image statistics within tolerance.

CPU, small sizes inside the check.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief. The check must pass in the Linux judge image, where there is no GPU.
- No quick fixes: speed comes from better algorithms and data paths, never from lower quality, fewer samples than the defaults, smaller outputs, or skipped work that the result needs.
- **Allowed files:**
  - the bridge modules of the tools named above and their helpers: scatter, ground cover, trees, liquids, materials, weather, atmosphere, render_final and render outputs;
  - `bench/**`, `test/**`, `bridge/tests/**`, `docs/**`.
  - Not the landform modules, `heightfield` or `erode`, which the `landforms` job owns and speeds up itself.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the full benchmark at the base commit and with the patch in the judge image. The patch is at least 5 times faster in total, and its render matches the base render.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
