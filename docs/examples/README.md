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
