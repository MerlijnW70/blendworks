# Job: Every bridge command finishes or stops within a budget

Bridge commands run synchronously on Blender's main thread, and nothing on the Python side can stop a long one: the timeout is only advertised to the Node client, which can stop waiting but not stop the work. An audit found argument sets that hang a session or exhaust memory: `erode` allows about 2·10¹⁰ droplet steps, and its brush allocates `(2·reach+1)² × 512` elements (radius 1000 m at 1 m spacing is about 16 GB); `lsystem` allows 100 iterations at a million modules; `grow_tree` colonisation compares every attractor with every new node each step; `fracture` seeds and Voronoi cells loop in pure Python; the noise stack evaluates all points of up to 12 octaves of Worley noise at once; shape builders check the vertex cap only after building. Make every command's work bounded and cancellable, with the scene rolled back when a budget stops it.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Cooperative budget:** the handler gives each command a deadline derived from its policy timeout (`ctx.deadline`, `ctx.tick()`); long loops call `tick()` once per batch, round or iteration; when the deadline passes, the command stops with a clear `budget` error naming the command, the elapsed time and how to reduce the work, and the existing rollback restores the scene.
2. **Cost caps before work:** each heavy command estimates its cost from its arguments before allocating or iterating, and refuses with a message that states the estimate, the cap and which arguments to lower: erode (droplets × lifetime, brush footprint × batch), lsystem (derivation length per step, nodes), grow_tree (points × expected nodes), fracture (pieces, seed attempts), noise_displace and heightfield (points × octaves × basis cost), shell, lathe, sweep and other builders (vertex count from rings × points before building), scatter (candidates), realize/copies (vertices × copies).
3. **Memory:** the erosion brush footprint is capped (or the batch shrinks adaptively) so no array exceeds a stated element count; noise evaluation is chunked (for example 250,000 points per chunk) with identical results to the unchunked version.
4. **Spatial indexing where the audit found quadratic work:** tree colonisation's nearest-node search, fracture seed spacing, and scatter's minimum-distance report use a grid or KD-tree, with results identical to the current ones for fixed seeds.
5. **Docs:** `docs/DESIGN.md` states the budget model and every cap.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- A command forced past a short deadline stops with `budget`, and the scene is unchanged afterwards.
- Each cost cap refuses an over-budget argument set before any scene change and before large allocation (measure peak memory or allocation size in the test).
- Chunked noise equals unchunked noise bit for bit (or to a stated tolerance) on a fixed field.
- Indexed tree colonisation, fracture seeding and scatter reporting give the same results as before for fixed seeds, and are faster on a stated large case (report timings).

## Rules

- Follow `CONTRIBUTING.md`. Results for every existing test and example stay the same.
- **Allowed files:** `bridge/blendworks_bridge/handler.py`, `registry.py`, `policy.py`, `limits.py`, `kit_limits.py`, `transaction.py` only for the budget hook, and the heavy command and algorithm modules named above (`erosion_*.py`, `commands/erode.py`, `lsystem_*.py`, `commands/lsystem.py`, `tree_colonize.py`, `fracturing.py`, `polyhedron.py`, `commands/fracture.py`, `noise.py`, `noise_stack.py`, `builder.py`, shape modules, `poisson.py`, `scatter_plan.py`, `copies.py`, `meshdata.py`); `bridge/tests/**`, `test/**`, `docs/**`.
- **Files shared with other open jobs:** tree-mesh and tree-shape own the tree modules other than `tree_colonize.py`; if they land first, rebase.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs an over-budget call of each heavy command against a live bridge and sees a clean refusal or budget stop with the scene intact, and reruns every `docs/examples/*.py` script with unchanged summaries.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
