# Job: Tree meshes from skeletons: bark, flare, junctions and leaves

`grow_tree` grows a tree skeleton (format `blendworks.skeleton` version 1, documented in `docs/DESIGN.md`, "Tree skeletons") with a curve preview. A game- or film-ready tree needs one closed, UV-mapped bark mesh with smooth branch junctions, a flared trunk base and roots, and foliage. Build the mesh half of `grow_tree` (plan item P5, job B in `docs/research/natural-shapes.md`), from the cited papers.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`tree_mesh` command** (from any object that carries a version 1 skeleton, including one imported from a glb):
   - Parameters: `ring_segments` (by radius, with a minimum and maximum), `junction` (`skin`, `voxel`), `flare` (trunk-base flare amount and height), `root_flare`, `bark_noise` (a `noise_displace` stack in metres, amplitude bounded by a share of the local radius), `min_radius` (twigs thinner than this are dropped or turned into cards), `lod` (a target triangle budget), `keep_skeleton`.
   - **Method:** generalised cylinders along the skeleton with parallel-transport frames [S2], joined by an applied skin or voxel step [S22, S24], so the bark is one closed manifold shell with no internal faces, no self-intersections at junctions and no modifiers left.
   - **Radii:** the mesh radius at each node matches the skeleton radius within 10 % (outside the flare), so the pipe model survives into the mesh.
   - **UVs:** bark UVs in metres: `u` around the branch, `v` along it, continuous along each axis, with seams placed on the side away from a given view direction (default: facing −Y), so a bark material in metres does not stretch on thin or thick branches.
   - **Material slots:** bark, fresh wood for cut ends if `min_radius` drops twigs, roots.
   - The skeleton property and glTF `extras` are kept on the mesh object, so the judge can read them.
2. **`tree_leaves` command:** places leaf cards or a given leaf object on twig tips and along the last orders, with `density`, `size` and `size_by_order`, `phyllotaxis` divergence along twigs (default 137.5°), `align` (sun-facing with a factor), `seed`, within the instance limit, through the existing instance machinery. It must work with the `leaf` material preset (alpha cut-out and translucency).
3. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference, one short clause in `src/mcp/instructions.ts` (it is at its 4096-character limit), and a tree workflow from `grow_tree` to `tree_mesh` to `tree_leaves` to materials.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- The bark mesh is one closed manifold shell with consistent winding, positive volume and no modifiers, for a colonisation tree with roots and for a levels tree.
- The measured mesh radius at each node (rays around the node in its normal plane) is within 10 % of the skeleton radius outside the flare region.
- No self-intersections at junctions (a BVH overlap test of the mesh against itself, excluding adjacent faces).
- UV scale along `v` and around `u` stays within a stated band of metres per UV unit over all branches.
- With `lod`, the triangle count is within 10 % of the budget, and the radius test still holds for nodes thicker than `min_radius`.
- The skeleton survives `tree_mesh` and a glb export.
- `tree_leaves`: leaves sit at twig tips and along the last orders only, consecutive leaves along a twig differ by the divergence, the seed repeats.
- A full-judge test: the leafless bark mesh of the example oak passes `natural.surfaceRoughness` with the tree default (`flatShareMax`) and a cylinder-built tree fails it.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the papers; do not port Sapling (GPL-3.0-or-later) or tree-gen (GPL-3.0).
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, the tree modules (`tree_*.py`, `commands/trees.py`) and `gltf_extras.py` where reuse needs it, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** natural-rules-b owns `src/judge/**`, `bridge/judge/**`, `schemas/**`; lsystem owns its new modules. If several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that turns the oak, conifer and windswept skeletons of `docs/examples/grow_trees.py` into bark meshes with the `bark` material, adds leaves (broadleaf cards on the oak and windswept tree, needle clusters on the conifer), and reviews the renders at tree scale and in bark close-ups: smooth junctions, a flared base, no seams across the bark, foliage that reads as a crown.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
