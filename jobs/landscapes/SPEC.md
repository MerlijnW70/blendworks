# Job: Landscapes — mountain ranges, valleys, cliffs, strata, biomes and distant land

Blendworks builds terrain tiles from a noise stack (`heightfield`) and erodes them (`erode`), but a scene still ends at the edge of one small patch of land. There are no mountain ranges at kilometre scale, no valleys cut by rivers, no cliffs, overhangs or caves (a heightfield cannot overhang), no rock layers, no ground that changes by itself with slope, height and moisture, and no distant land to the horizon. Add landscapes that Blendworks builds itself, from a meadow to an alpine range, and that the trees, ground cover, rocks, water, sky and weather it already builds fit into.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; the `liquids` job lands before this one, so rivers and lakes come from its `liquid_body`.

## Required

1. **Landforms at real scale:** a `landscape` command builds a terrain region from metres to tens of kilometres with detail that falls off with distance from a camera or focus point (nested rings or tiles at decreasing resolution, no cracks or visible seams between levels), in named landforms at least: plains and rolling hills, mountain ranges with ridges and peaks (uplift with ridged noise and erosion, believable relief and slope statistics per landform, cited), river valleys and gorges, plateaus and mesas, canyons, coastal land with beaches and sea cliffs, dunes, and a volcano with a crater. Heights, relief and the ridge direction are parameters in metres and degrees, and the same seed repeats.
2. **Water shapes the land:** flow directions and flow accumulation over the terrain, river channels carved by stream-power erosion that run downhill without pits (depressions filled or drained into lakes), valleys whose cross-section follows the landform (V in mountains, wide floors in plains), and the channel lines handed to `liquid_body` as river and lake paths, so the water sits in its bed. A `flow`, `wetness` and `distance_to_water` attribute per vertex.
3. **Cliffs, overhangs and caves:** steep faces that a heightfield cannot hold: vertical and overhanging cliffs, sea arches and caves with an inside, built as a closed volume mesh (signed distance field or voxels meshed to triangles) blended into the terrain without holes or a visible seam, with UVs or triplanar texturing that does not stretch on vertical faces.
4. **Rock strata:** sedimentary layers by depth with their own colour and hardness, dip and strike in degrees, that the erosion respects (hard layers form ledges and terraces, soft layers recede), visible as bands on cliffs, canyon walls and mesas; plus granite, basalt (with columns) and volcanic rock where the landform asks for it.
5. **Ground by itself:** a terrain material that picks its surface from slope, height, curvature, flow, wetness and exposure: rock on steep slopes, scree and talus below cliffs, soil and grass on gentle slopes, sand on beaches and in dunes, mud and wet ground along water, snow above a snow line that follows slope and aspect, with soft natural transitions and no tiling at any distance (cited reference values for the snow line, angle of repose of scree and sand, and the like).
6. **Biomes:** named biomes at least temperate meadow, mixed forest, alpine, desert, canyon, coast, volcanic and snow, each setting the landform defaults, the ground materials, and the vegetation and rock populations: tree species and density from the existing tree tools, `ground_cover` presets, boulders and scree from the rock tools at cliff feet and on talus slopes, all masked by slope, height, wetness and distance to water so nothing grows on cliffs or in water. Transitions between biomes over a region are smooth.
7. **Distant land and horizon:** land to the horizon without an HDRI: distant ranges and hills at decreasing detail, forest and tree lines as cheap cards or impostors baked from Blendworks trees, aerial perspective from `atmosphere` and the `sky` so far ridges fade to the sky colour, and the curvature of the earth for ranges tens of kilometres away; within a stated triangle and memory budget. This replaces the open `backdrop` job's distant terrain.
8. **Working with what exists:** the `sky` and `clouds` light and shadow the land (cloud shadows sweep over ranges), `weather` wetness darkens and snow whitens the ground by its rules, `liquid_body` water sits in the carved beds, `scatter`, `ground_cover` and the tree tools read the biome and mask attributes, `render_final` renders a landscape at its default settings, and the shared wind direction is one value.
9. **Docs and MCP:** command reference, a "landscapes" workflow with each landform and biome and its look, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: neighbouring detail levels share their border heights within a stated tolerance and the mesh has no holes; each landform's relief and slope distribution falls in its stated, cited range and differs from the others; flow accumulation drains every cell to an outlet or a lake with no pits left, and a carved river descends monotonically along its path; a river from `liquid_body` lies inside its channel; a cliff face reaches at least a stated overhang and the volume mesh is closed and joins the terrain without gaps; hard strata stand out as ledges after erosion while soft strata recede; the ground material is rock above a stated slope, sand within a stated distance of a beach, snow above the snow line and not below it, and wet near water; vegetation and ground cover are absent on cliffs and in water and their density follows the biome; distant land fades towards the sky colour with distance by the atmosphere's extinction within a stated tolerance; the triangle count stays within the stated budget; the same seed repeats and another seed changes the land. Small grids, small render sizes and sample counts, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds every landscape itself: no downloaded heightmaps, DEMs, textures, HDRIs or models in presets or tests.
- Weather simulation over geological time, glaciers and plate tectonics as simulations are out of scope; landforms may imitate their results.
- **Allowed files:** `bridge/blendworks_bridge/terrain.py`, `heightgrid.py`, the `heightfield` and `erode` commands, new bridge modules and commands for landscapes, the scatter, ground-cover and tree placement mask code where biomes plug in, the `weather` wetness and snow code where the ground needs it, `atmosphere` only where distant land needs it, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds five landscapes with Blendworks only and renders them with `render_final` under the `sky` at a fitting time of day: an alpine valley with a river into a lake below snowy peaks and forest on the slopes; a desert canyon with layered walls and scree; a sea coast with cliffs, an arch, a beach and waves; a volcano with dark basalt and sparse vegetation; and rolling farmland hills fading to distant ranges. Each is compared with CC0 reference photos of the same kind of place and reads as a photograph, with land to the horizon and nothing floating, nothing growing on cliffs or in water.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
