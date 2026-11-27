# Job: Surface — ground that chooses itself, snow, biomes and vegetation that belong

Terrain from `landscape` and `cliffs` carries its shape, strata and lithology, but its ground is one material and its plants are scattered by hand. Real ground follows rules: rock where it is too steep for soil, scree below cliffs, soil and grass on gentle slopes, sand on beaches, mud along water, moss and lichen on shaded damp rock, snow where it can stay. Vegetation follows height, slope, aspect and water, with a tree line and gradual transitions. Add ground, snow and living cover that a landscape chooses for itself. Third of four landscape jobs (`landforms`, `cliffs`, `surface`, `horizon`).

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; `landforms` lands before this job and `cliffs` may land before or during it.

## Required

1. **Ground by rules:** a terrain material that picks and blends its surface per point from slope, height, curvature, aspect, flow, wetness, distance to water, lithology and the rockfall attributes: bare rock of the right lithology on steep slopes, scree and talus, soil, grass, sand on beaches and dunes, gravel in channels, mud and wet ground along water and in hollows, with soft, noisy, natural transitions (no straight bands, no contour-following edges), with the angles, heights and distances as cited parameters. No visible tiling at any distance: macro colour variation over hundreds of metres, meso over metres, micro detail up close.
2. **Weathering:** moss and lichen on shaded, damp, north-facing rock and in cracks, desert varnish on dry rock, water stains below ledges, a wet dark band along rivers, lakes and the tide line, using the `weather` wetness state.
3. **Snow that behaves:** snow cover from a snow line in metres that varies with aspect (lower on shaded faces), absent above a stated slope (about 50 degrees, cited), deeper in hollows and on the lee side of ridges by the scene's wind, avalanche tracks and cones below steep gullies, cornices on lee ridges, thinning to patches at its edge; snow as geometry where it is deep and as a material where it is thin, and the `weather` snow state drives it.
4. **Biomes:** named biomes at least temperate meadow, mixed forest, conifer forest, alpine, desert, canyon, coast, volcanic, wetland and snow, each setting the ground rules, the weathering, and the populations of trees (from the existing tree tools and species), shrubs, `ground_cover` presets and rocks, by height, slope, aspect, moisture and distance to water, with smooth ecotones between biomes across a region.
5. **Vegetation that belongs:** a tree line at a stated height that varies with aspect, with stunted, sparser, wind-shaped trees just below it; forest edges with shrubs; trees absent on cliffs, scree and in water; riparian vegetation (reeds, willows) along water; density, species and size following moisture and slope; clumping and spacing like real stands (cited spacing statistics); everything instanced within a stated memory budget.
6. **Seasons:** a `season` value (spring, summer, autumn, winter) that changes grass colour, leaf colour and leaf drop, flowers and snow together, consistent across the landscape.
7. **Working with what exists:** `ground_cover`, `scatter` and the tree tools take the biome populations; `weather` wetness and snow, `liquid_body` shores and `cliffs` overhangs and talus are read, not duplicated; `render_final` renders it at its default settings.
8. **Docs and MCP:** command reference, a "biomes" workflow with each biome, season and its look, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: the ground is rock above a stated slope and soil or grass below it; sand lies within a stated distance of a beach; ground near water is wet and darker by a stated factor; transitions are not straight (a measured edge irregularity above a stated value); a tiling measure (autocorrelation peak at the texture period) stays under a stated value at three distances; moss is denser on shaded damp faces than on sunny dry ones; snow is absent above the stated slope and below the snow line, lower on shaded faces, deeper in hollows and on lee sides; the tree line follows its height and aspect; nothing grows on cliffs, scree or in water; biome densities match their parameters and ecotones are gradual; `season` changes colours and snow consistently; the same seed repeats. Small grids and renders, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds every surface itself: no downloaded textures, scans or models.
- **Allowed files:** new bridge modules and commands for terrain materials, snow and biomes, the procedural material presets where ground layers need them, the scatter, ground-cover and tree placement code where biomes plug in, the `weather` wetness and snow code, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds with Blendworks only an alpine slope from valley forest through the tree line to snowy rock, a desert canyon floor, a coast with dunes and a beach, a wetland along a river, and the same alpine slope in all four seasons, renders each with `render_final` from a wide view and from two metres, and compares them with CC0 reference photos: each reads as a photograph of that place and season.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
