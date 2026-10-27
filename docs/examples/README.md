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
