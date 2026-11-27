# Job: Landforms — mountains, valleys, coasts and volcanoes shaped like the real Earth

Blendworks builds terrain tiles from a noise stack (`heightfield`) and erodes them with droplets and talus (`erode`), but noise mountains do not look like mountains. Real land is shaped by processes that leave signatures geomorphologists measure: rivers carve dendritic networks and V-shaped valleys, glaciers carve U-shaped troughs, cirques and arêtes, sediment builds fans, floodplains, meanders and deltas, hard rock layers stand as ledges, waves cut platforms and stacks. Add landforms at real scale, shaped by those processes and checked against published measurements of real terrain. This is the first of four landscape jobs: `landforms` (this), `cliffs` (overhangs, caves, close-up rock), `surface` (ground materials, snow, biomes, vegetation), `horizon` (distant land and the finished scenes).

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; the `liquids` job lands before this one, and rivers and lakes come from its `liquid_body`.

## Required

1. **A region at real scale:** a `landscape` command builds a terrain region from tens of metres to at least 30 km across, with detail that falls off with distance from a focus point or camera (nested levels at decreasing resolution, no cracks, seams or popping lines between levels), holding at least 0.5 m spacing near the focus. The region keeps the elevation grid and its attributes so later commands (and the `cliffs`, `surface` and `horizon` jobs) can read and refine it. Same seed, same land; another seed, other land.
2. **Uplift and fluvial erosion:** relief that comes from a process, not from noise alone: tectonic uplift fields (ranges with a ridge direction, domes, escarpments, plateaus) eroded by a stream-power law (erosion rate proportional to drainage area to the power m times slope to the power n, with m/n near 0.5, cited) plus hillslope diffusion and thermal failure, run on a coarse grid for geological time steps and refined with detail noise that follows the drainage. Flow routing (D8 or multiple flow direction), depression filling or breaching so every cell drains to an outlet or a lake, and per-vertex `flow`, `drainage_area`, `stream_order` and `distance_to_channel` attributes.
3. **Glacial landforms:** for alpine land, glaciated valleys with U-shaped cross-sections, cirques at valley heads, arêtes and horns between them, hanging side valleys above the main trough, and moraines and a lake at the former glacier front, controlled by an equilibrium line altitude in metres. A preset can mix glacial upper valleys with fluvial lower valleys, as in the Alps.
4. **Sediment and rivers in the lowlands:** deposition where the stream power drops: alluvial fans at mountain fronts, flat floodplains, meandering channels with point bars and oxbow lakes, braided channels on steep gravel plains, terraces along incised rivers, and deltas where a river meets a lake or the sea. River paths, widths, depths and lakes are handed to `liquid_body` so the water lies in its bed; waterfall and rapids positions (where a channel crosses a step) are reported for later use.
5. **Rock strata and lithology:** layers by depth with their own hardness and colour, dip and strike in degrees, that the erosion respects (hard layers form cliffs, ledges and caprock mesas, soft layers recede into slopes), and lithology classes (sedimentary layers, granite, basalt, volcanic ash) stored per vertex as attributes for the `surface` job.
6. **Named landforms:** presets at least for plains, rolling hills, a fluvial mountain range, an alpine glaciated range, a river valley and gorge, a plateau with mesas and buttes, a layered canyon, a sea coast (wave-cut platform, sea cliffs, beach, sea stacks positions, bay and headland), dunes (barchan and transverse, by wind direction, slip faces at the angle of repose), and a volcano (stratovolcano and cinder cones, crater, lava flow tongues, ash slopes). Each preset is documented with the processes and parameter values it uses.
7. **Measured against real land:** for each landform preset, the hypsometric integral, the slope distribution (mean and spread), the drainage density, Hack's law exponent, the Horton bifurcation ratio and the valley cross-section shape (V or U, by a fitted power-law exponent) fall in ranges cited from published geomorphometry of real terrain of that kind. No downloaded elevation data in presets or tests: the reference values are numbers with sources.
8. **Working with what exists:** `liquid_body` puts rivers and lakes into the carved beds; `scatter` and `ground_cover` and the tree tools can read every attribute as a mask; `erode` and `heightfield` keep working and can refine a region's tiles; `render_final` renders a region at its default settings; the scene's wind direction from `weather` sets the dune direction when asked.
9. **Docs and MCP:** command reference, a "landforms" workflow with each preset, its processes and its look, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: neighbouring detail levels share border heights within a stated tolerance and the surface has no holes; the same seed repeats and another changes the land; after routing no cell is a pit except lakes and every cell reaches an outlet; channel elevation falls monotonically downstream; the slope–area relation of channels follows the stream-power exponent within a stated tolerance; a glaciated valley's cross-section fits a U (power-law exponent near 2) and a fluvial one a V; fans and deltas sit where stream power drops; meanders have a stated sinuosity range; hard strata stand out as ledges after erosion while soft strata recede; dunes have slip faces at the angle of repose and orient by the wind; each preset's geomorphometric measures fall in its cited ranges and differ from the other presets; a river from `liquid_body` lies inside its channel; the triangle count and memory stay within stated budgets. Small grids, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds every landform itself: no downloaded heightmaps, DEMs, textures or models in presets or tests.
- Overhangs, caves, arches and close-up rock detail are the `cliffs` job; ground materials, snow and vegetation are the `surface` job; distant land to the horizon is the `horizon` job. This job leaves clean attributes and an API for them.
- **Allowed files:** `bridge/blendworks_bridge/terrain.py`, `heightgrid.py`, the noise stack, the `heightfield` and `erode` commands, new bridge modules and commands for landforms, the `liquid_body` path input where rivers and lakes plug in, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds with Blendworks only an alpine valley (glacial trough with a river into a lake), a layered canyon with mesas, a sea coast, a volcano with cinder cones, and a meandering lowland river, renders each with `render_final` in clay shading from an aerial and a ground-level view, and compares the forms with CC0 reference photos and published figures of real places of that kind: each landform reads as the real thing by its shape alone.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
