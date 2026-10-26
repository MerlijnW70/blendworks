# Asset job: a set of cave rocks

Build a set of three game-ready 3D cave rocks in Blender and deliver them as one binary glTF (`.glb`), each rock as its own object.

## Look

Three rocks for a top-down underground game: a large boulder, a medium rock and a small rock, placed side by side in a row along X with small gaps.
- Each rock has a faceted, natural, irregular shape, not a sphere or a box, with chipped edges and some flat faces.
- Cool grey stone with a slightly lighter and a slightly darker stone material, so the faces read.
- One of them has a few small inlaid ore crystals in a second, copper-orange material.

## Rules (checked by the Blender judge)

The asset spec below is checked exactly by `blendworks judge`:

```json
{
  "name": "cave rocks",
  "format": "glb",
  "triangles": { "max": 1500 },
  "size": { "x": [1.6, 2.6], "y": [0.5, 1.0], "z": [0.3, 0.8] },
  "origin": "bottom-centre",
  "manifold": true,
  "materials": { "min": 2, "max": 3 },
  "uv": { "required": true, "maxOverlap": 0.1 },
  "objects": { "min": 3, "max": 3 },
  "fileSize": { "maxBytes": 3000000 },
  "views": ["front", "top", "three-quarter"],
  "brief": "Three faceted cave rocks (large, medium, small) in a row, grey stone, one with copper ore crystals."
}
```

## Acceptance

1. `blendworks judge` passes every rule.
2. The judge views the contact sheet. The rocks must look natural and distinct from one another, not like spheres or boxes.

## Deliver

- The `.glb` and the Blender Python script that builds it from an empty scene.
- Announce the `.glb`'s sha256 to the judge.
