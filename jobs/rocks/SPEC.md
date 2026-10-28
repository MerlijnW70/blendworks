# Job: Rocks that fracture, chip and wear like real stone

A displaced sphere reads as a displaced sphere: the natural judge rules now fail it on solidity and roughness (`natural.solidity`, `natural.surfaceRoughness`). Real rocks are either fresh, blocky fragments with about 6 faces and 8 vertices, or worn ones whose edges rounded first while their large faces stayed. Blendworks has no remesh, no implicit shapes and no fracture. Build plan items P6 (`remesh`, `blob`) and P7 (`fracture`, `chip`, `abrade`) of `docs/research/natural-shapes.md`, from the cited papers.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`remesh`:** `name`, `voxel_size` (metres), `adaptivity`, `smooth_shading`. It applies the Remesh modifier in voxel mode at once, because the judge refuses an unapplied remesh. It refuses a voxel size that would exceed the bridge's vertex limit, before it runs.
2. **`blob`:** `points` with a `radius` each, `threshold` and `voxel_size`. A smooth union of spheres as metaballs [S19, S20], converted to a mesh and remeshed, so the result is one closed mesh with no modifiers.
3. **`fracture`:** `name`, `pieces`, `mode` (`binary`, `voronoi`), `seed`, `min_size`, `keep_original`.
   - `binary` splits the largest piece by a random plane through a point near its centroid, again and again; `voronoi` builds cells by bisector planes [S15], with seed points inside the object.
   - Cutting is exact: either the exact `boolean` or a half-space clip of a convex input, stated in the docs. Every piece is a closed solid; pieces of a convex input are convex.
   - Pieces get new UVs on the cut faces that continue a box mapping in metres, and a separate material slot for the fresh faces, so a fresh-break material can be assigned.
4. **`chip`:** `name`, `count`, `depth` (metres), `seed`: random planar cuts across edges and corners of the given depth, exact, leaving a closed solid.
5. **`abrade`:** `name`, `amount` or `target_convexity`, `iterations`, `seed`: curvature-weighted smoothing that moves high-curvature vertices first, so edges round while large faces stay [S18]. It must keep the mesh closed and must not shrink the object by more than a stated share.
6. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference, `src/mcp/instructions.ts`, and a rock workflow that says when to use fracture, chip, abrade, `noise_displace` and `remesh`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- `remesh` of a cube with a hole gives one closed manifold shell with a volume within 2 % of the input, and no remaining modifiers.
- Two blobs with overlapping radii give one shell, and far-apart ones give two.
- `fracture`: the volumes of the pieces add up to the original within 0.5 %; every piece is closed; pieces of a convex input are convex; no unmapped faces.
- With `binary` and 200 pieces, the mean face and vertex counts of the pieces (planar regions merged at 1°) lie within 20 % of `[6, 8]` [S17: measured `[6.63, 8.93]`].
- `chip` keeps a closed solid and removes volume only near edges (no removed point is farther than `depth` from the original surface's edges).
- `abrade` reduces the 90th percentile of the normal deviation (the natural judge's roughness measure, `extent/32`), while the bounding-box axes change by less than 5 % in its first phase [S18].
- A rock built by `fracture` → `chip` → `abrade` → `noise_displace` passes the calibrated `natural` rock defaults through the full judge, and a plain displaced sphere fails them.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Use the ideas of the papers; Cell Fracture is GPL, so do not copy its code.
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** scatter owns new placement modules, `instancing.py` and `commands/placement.py`; natural-materials owns `presets.py`, the material modules and `commands/materials.py`, `commands/procedural.py`. If several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that builds a set of fresh and worn rocks (a fractured boulder with its fragments, chipped and abraded stones) and reviews the renders and the natural-rule scores.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
