# Job: Cliffs — overhangs, caves, arches and rock that holds up close

A heightfield cannot overhang, so terrain from `landscape` has no vertical or overhanging cliffs, no caves, arches or sea stacks, and seen from two metres its rock is a smooth stretched surface. Real cliffs are broken by joints, bedding and fractures, with blocks, ledges and talus below them sorted by size. Add the steep and hollow parts of a landscape and the close-up rock detail, built on the region and attributes that the `landforms` job leaves. Second of four landscape jobs (`landforms`, `cliffs`, `surface`, `horizon`).

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; `landforms` lands before this job, and this job builds on its `landscape` region, strata and lithology attributes.

## Required

1. **Volume terrain:** where the land needs it, a closed volume mesh (signed distance field or voxels, meshed to triangles with sharp features kept) that holds vertical and overhanging cliffs, caves with an inside and an end, natural arches, sea stacks, rock towers and hoodoos, blended into the heightfield terrain without holes, cracks or a visible seam, and with the same level-of-detail falloff as the region.
2. **Structure of rock:** cliffs shaped by their lithology from `landforms`: bedding planes and ledges in sedimentary layers, joint sets in two or three directions (strike and dip in degrees) that break faces into blocks and chimneys, columnar jointing in basalt (mostly hexagonal columns of a stated width range), rounded exfoliation in granite, and fresh scars where blocks have fallen.
3. **Detail at every distance:** geometric detail that holds from 100 m down to 0.5 m: fractures, chips, pits and grain displaced in metres, with adaptive subdivision or displacement at render time near the camera and none far away, so a close-up of a cliff or boulder reads as rock and not as a smooth stretched mesh, within a stated triangle and memory budget. Texturing on steep and overhanging faces by triplanar or volume coordinates with no stretching.
4. **Rockfall and talus:** talus cones and scree slopes at the foot of cliffs at the angle of repose (cited), with blocks sorted by size (the largest travel furthest), boulders that sit embedded in the ground by a stated fraction of their height and rest stably (no floating, no interpenetration), built from the existing rock tools (`fracture`, `chip`, `abrade`) and placed by the cliff's own rockfall.
5. **Coast and water at rock:** sea caves and arches at the water line, wave-cut notches, a smooth wet band where waves reach, and pools in hollows; waterfalls positions from `landforms` get a plunge pool and a wet, darkened splash zone.
6. **Working with what exists:** `liquid_body` water fills caves and pools that open to it; `scatter`, `ground_cover` and the tree tools never put plants on vertical or overhanging faces or inside caves unless asked; the attributes (`slope`, `overhang`, `exposure`, `rockfall`) are readable as masks for the `surface` job; `render_final` renders it at its default settings.
7. **Docs and MCP:** command reference, a "cliffs and caves" workflow with each form and its look, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: the volume mesh is closed and manifold and joins the terrain with no gap wider than a stated tolerance; a cliff reaches a stated overhang; a cave has an inside reachable from its mouth; an arch has an opening; joint faces follow the stated strike and dip within a stated angle; basalt columns have a stated width range and are mostly six-sided; displacement amplitude near the camera is at least a stated value and far away zero; texture stretch on vertical faces stays under a stated factor; talus slopes lie at the angle of repose within a stated tolerance and block size grows downslope; no boulder floats or interpenetrates; nothing grows on overhangs; the triangle and memory budgets hold; the same seed repeats. Small grids and renders, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds every rock itself: no downloaded scans, textures or models.
- Ground materials, moss, lichen and snow on the rock are the `surface` job; leave clean attributes for them.
- **Allowed files:** new bridge modules and commands for volume terrain, cliffs, caves and talus, the `landscape` region code only where volumes join it, the rock tools (`fracture`, `chip`, `abrade`) where talus needs them, the scatter, ground-cover and tree placement mask code where overhangs plug in, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds with Blendworks only a sea cliff with an arch, a stack and a sea cave; a layered canyon wall with ledges and talus; basalt columns; a granite dome with a boulder field; and a limestone cave mouth, and renders each with `render_final` from a distance and from two metres. Compared with CC0 reference photos of the same kind of rock, each reads as a photograph at both distances.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
