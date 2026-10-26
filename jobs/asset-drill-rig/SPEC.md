# Asset job: a steam-powered ore drill rig

Build a highly detailed, game-ready 3D steam drill rig in Blender and deliver it as a binary glTF (`.glb`). Detail is the point of this job: every part should look machined, assembled and used, with no plain boxes or flat untreated faces.

## Look

A compact steam drill rig that a mining crew wheels up to a rock face in an underground game.
- **Chassis:** a riveted iron frame on four spoked wheels with tyres and hub caps. The frame has bevelled edges, gussets at the corners and a tow hitch at the back.
- **Boiler:** a horizontal boiler with banded seams, a row of rivets on every band, a firebox door with hinges and a latch, and a short smokestack with a flared cap.
- **Drivetrain:** a visible gear train of at least three meshing gears with real teeth (not textures). A piston and connecting rod drive the main gear, and a chain or belt runs over sprockets to the drill head.
- **Drill head:** a long drill bit with spiral flutes and a hardened tip, in a bearing housing held by bolts.
- **Plumbing:** brass pipes with real bends, flanges with bolts at each joint, and at least two valve wheels with spokes.
- **Instruments:** a pressure gauge with a glass face, a dial with tick marks, a needle and a bezel. Add a whistle and a lever with a grip.
- **Small parts and wear:** hex bolts with washers, a coal shovel or toolbox hung on the frame, an oil can and a hanging lantern. Show wear through the material split: worn edges, soot near the stack and rust patches.
- **Materials:** dark iron, brass, copper, worn steel, rubber or leather, wood (the handles and toolbox), gauge glass, and an emissive warm glow inside the firebox.

Every part must read in the judge's renders. Detail too small to see at the judge's resolution does not count, so prefer bold, well-shaped forms with bevels over noise.

## Rules (checked by the Blender judge)

The asset spec below is checked exactly by `blendworks judge`:

```json
{
  "name": "steam drill rig",
  "format": "glb",
  "triangles": { "min": 40000, "max": 150000 },
  "size": { "x": [1.2, 2.0], "y": [0.7, 1.2], "z": [1.0, 1.6] },
  "origin": "bottom-centre",
  "manifold": true,
  "materials": { "min": 8, "max": 14 },
  "uv": { "required": true, "maxOverlap": 0.05, "minCoverage": 0.4 },
  "objects": { "min": 1, "max": 80 },
  "fileSize": { "maxBytes": 15000000 },
  "views": ["front", "back", "left", "right", "top", "three-quarter"],
  "brief": "A highly detailed steam drill rig: riveted frame on spoked wheels, banded boiler with smokestack and glowing firebox, meshing gears with real teeth, piston and chain drive, fluted drill bit, brass pipes with flanges and valve wheels, pressure gauge, lantern, tools and wear."
}
```

## Acceptance

1. `blendworks judge` passes every rule.
2. The judge views the contact sheet plus its own close-up renders of the gears, the gauge, the drill head and the boiler seams. Every item in the look list must be present, modelled in geometry and visible. Gear teeth, rivets, bolts, the gauge ticks and the drill flutes must be real geometry.
3. No part may be a bare box or cylinder without bevels, insets or attached detail. Triangles must go into visible shape, not hidden interior faces or needlessly dense flat surfaces.

## Deliver

- The `.glb` and the Blender Python script that builds it from an empty scene, with every detail generated in code.
- Announce the `.glb`'s sha256 to the judge.
