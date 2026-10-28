# Examples

## Engraved rings

`engraved_rings.py` builds an engraved brass ring pair on a marble plinth with Blendworks commands only, and renders close-ups. It is the acceptance build of the `modeling-3` job.

```
blender --background --factory-startup --python docs/examples/engraved_rings.py -- out
```

The script writes into `out`:
- `engraved-rings.blend`;
- six close-up PNGs (`BLENDWORKS_DEVICE` picks the render device, `auto` by default);
- `summary.json`: every command with its time, solver and mesh quality.

It runs these steps in order, and stops at the first failing command:
1. **Horizon ring.** 360 tick marks in one `engrave_scale` call (majors every 10 degrees, half-length marks every 5), 24 numbers and the 12 zodiac signs, one `engrave` call each.
2. **Meridian ring.** A quadrant-mirrored 0-90 scale and 40 numbers.
3. **Union.** An exact `boolean` union of the two engraved rings, with `manifold: true`.
4. **Materials.** `brass` with `age: aged` and `scratch_direction: v`, which follows both rings along their paths, and `marble`.

`summary.json` shows that every cut left the mesh closed, with no slivers, and which solver the union used.

## Noise terrain

`noise_terrain.py` builds a 2 x 2 set of 100 m terrain tiles with ridged, domain-warped noise and a rock made with `noise_displace` on a subdivided ico sphere, with commands only, and renders close-ups. It is the acceptance build of the `noise-terrain` job.

```
blender --background --factory-startup --python docs/examples/noise_terrain.py -- out
```

The script writes into `out`:
- `noise-terrain.blend`;
- five PNGs: `overview` (shaded), `overview-clay`, `ridge-detail`, `tile-joint` (clay, at the corner where the four tiles meet) and `rock`;
- `summary.json`: every command with its time, mesh size and height range.

It runs these steps in order, and stops at the first failing command:
1. **Tiles.** Four `heightfield` calls with the same seed and noise (`mode` ridged, `hurst` 0.7, `scale` 150 m, seven octaves, a 45 m warp) and tiles `[0, 0]` to `[1, 1]`, each with a skirt, so they join along their edges and close into solids. The finest wavelength (150 / 2^6 = 2.3 m) is more than two vertex spacings (1 m).
2. **Rock.** An ico sphere flattened with `transform` and `apply_transform`, then three `noise_displace` passes: billow lumps at 2.6 m, worley ridged cracks at 1.1 m, and fine perlin grain at 0.3 m.
3. **Materials and renders.** Stone presets, then the five renders.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Scatter rocks

`scatter_rocks.py` scatters a rock set over a 100 m `heightfield` tile with commands only and renders it. It is the acceptance build of the `scatter` job.

```
blender --background --factory-startup --python docs/examples/scatter_rocks.py -- out
```

The script writes into `out`:
- `scatter-rocks.blend`;
- four PNGs: `overview`, `slope` and `closeup` (shaded), and `top` (clay, looking straight down, where the spacing shows);
- `summary.json`: every command with its time and, for `scatter`, the count, the smallest pairwise distance, the masked-out share and the fitted exponent.

It runs these steps in order, and stops at the first failing command:
1. **Terrain.** One `heightfield` tile with a skirt and the `slope` and `height` attributes, and a ground material.
2. **Rocks.** Three ico spheres, each flattened, shaped by three `noise_displace` passes and given its base at the origin with `set_origin` to `bottom_centre`, so the origin is the point that touches the ground.
3. **Scatter.** One `scatter` call with the three rocks as `sources`, `min_distance` 0.6 m (the 2 m rock footprint at the smallest scale 0.3), a `slope` mask that keeps faces up to 38 degrees, a `power` size distribution with exponent -2 from scale 0.3 to 2.4, `align` blend, a 6 degree tilt and an `embed` of 0.22. The source rocks are deleted afterwards; the copies keep sharing their meshes.
4. **Renders.** Four views.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Natural dressing

`natural_dressing.py` dresses the terrain and rock of `noise_terrain.py` with natural materials, with commands only, and renders close-ups. It is the acceptance build of the `natural-materials` job.

```
blender --background --factory-startup --python docs/examples/natural_dressing.py -- out
```

It adds to the terrain and rock:
- **Soil with moss.** `soil` on the terrain, and a `moss` layer through `up_facing`, `slope` (at most 38 degrees from horizontal) and `noise` masks combined with `with_masks`, so moss grows in patches on the gentle, upward-facing ground.
- **Stone without patches.** `stone` on the rock with its default soft colour patches, and a moss layer on its top.
- **A bark log** (`bark`, grain along the cylinder axis) and **a leaf card** (`leaf` with `cutout`, from its UV square). They stand at y -30, beside the terrain tiles and not in front of them: the 110 m tall terrain shades anything close behind it in the preview light, which made the log close-up almost black.

The close-ups are `rock`, `rock-top`, `log`, `leaf`, `ground-close` and the overview views of `noise_terrain.py`.

## Eroded terrain

`eroded_terrain.py` builds a 2 x 2 set of 100 m tiles from `heightfield`, erodes them as one grid with `erode` (hydraulic droplets, then thermal talus slides), dresses them with one `material_nodes` graph masked by the `slope`, `erosion` and `deposition` attributes, and renders them in low sun, with commands only. It is the acceptance build of the `erode` job.

```
blender --background --factory-startup --python docs/examples/eroded_terrain.py -- out
```

The script writes into `out`:
- `eroded-terrain.blend`;
- five PNGs: `overview` and `channels` (shaded and clay, from a camera and a low sun) and `tile-joint-clay` (the corner where the four tiles meet);
- `summary.json`: the `erode` reply (volumes eroded, deposited and carried off the edge, thermal sweeps, time) and every command with its time.

It runs these steps in order, and stops at the first failing command:
1. **Tiles.** Four `heightfield` calls with the same seed and gentle fBm (`scale` 140 m, five octaves, `hurst` 0.9, 35 m of height), tiles `[0, 0]` to `[1, 1]`, with `slope` and `height` attributes. The relief is gentle on purpose: slopes well below the talus angle leave the droplets room to cut gullies, and the thermal sweeps then only trim their walls.
2. **Erosion.** One `erode` call with `name` and the other three tiles in `names`: 300,000 droplets (capacity 3, `erode_rate` 0.02, `deposit_rate` 0.1, `inertia` 0.1, 200 steps of 1 m, the smallest brush) in 20 rounds, each followed by thermal sweeps at a 40 degree talus angle. The outer edge of the 200 m grid stays as built; the three inner edges are eroded as part of the grid and the tiles still share them exactly (`edge_change` 0).
3. **Materials.** The tiles are joined and welded along their shared edges (so shading has no seam), then one `material_nodes` graph mixes soil towards rock where `slope` is steep, towards pale scoured rock where `erosion` is deep and towards silt where `deposition` is thick.
4. **Renders.** A sun at 25 degrees, a world colour and three cameras, then the five renders.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_DROPLETS`, `BLENDWORKS_SWEEPS`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.
