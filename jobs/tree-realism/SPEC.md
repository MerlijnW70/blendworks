# Job: Trees that pass for photographs

Blendworks grows tree skeletons, meshes bark with flare and junctions, adds leaves and shapes trees by gravitropism, gnarl and wind. In a scene with an HDRI sky and scanned textures the trees still read as CG: crowns are too sparse and leaves too large and identical; the willow's hanging strands are evenly spaced and equally long, like a comb; there is no leaf colour, size, age or orientation variation; leaf cards use one texture; and twigs carry no small leaf clusters, so the crown silhouette is not filled. Make the defaults and presets produce trees that read as real at mid and close range.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Foliage density and clustering:** leaves arranged in clusters along the last two orders with realistic leaf area index per crown volume; silhouette gaps and depth that resemble real crowns; a measured crown "fill" statistic (for example the share of the crown silhouette covered from the judge's views) within a band calibrated on CC0 tree scans.
2. **Variation:** per-leaf size, hue, saturation, brightness, age (young/old), damage and curl variation, seeded; several leaf shapes per species preset; back-face translucency and subsurface tint; sun-facing bias for outer leaves.
3. **Irregular hanging strands:** weeping presets vary strand length, spacing, thickness and sway, with strands that branch occasionally and respond to the crown shape, so no comb pattern is visible; a measured regularity statistic (for example the coefficient of variation of strand spacing and length) above a threshold.
4. **Twigs and fine branches:** a twig level beyond the skeleton's tips (cards or geometry) so the crown edge is fine-textured rather than leaf-ended.
5. **Species presets:** oak, birch, pine, willow, maple and olive presets that combine skeleton, form, bark, leaves and twig settings, documented with their reference photos (CC0 sources cited).
6. **Performance:** leaf and twig instancing within the instance budget; LOD-friendly export.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include the crown fill band, the strand regularity statistic, per-leaf variation present (non-zero spread in each varied attribute), seeds repeat, and the natural judge rules (Leonardo, surface roughness for trees, repetition) still pass on the presets. Container-friendly sizes; no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image). Write from papers and observation; do not copy GPL tree generators.
- **Allowed files:** the tree modules (`tree_*.py`, `commands/trees.py`, `commands/tree_mesh.py`, `commands/tree_leaves.py`), leaf and bark material presets, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, on Windows and in the judge image.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders each species preset at mid and close range under an HDRI with scanned bark, next to a CC0 photo reference of that species, and judges whether they read as real.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
