# Asset job: a standing torch

Build a game-ready 3D standing torch in Blender and deliver it as a binary glTF (`.glb`).

## Look

A standing torch for a top-down underground game:
- a wooden pole on a small stone or iron base;
- an iron cage or bowl near the top;
- a stylised flame of a few overlapping low-poly shapes, with an emissive warm orange-yellow material that glows.
It should read clearly from above and from a three-quarter view. Use dark wood, iron grey, and a flame that is bright and warm.

## Rules (checked by the Blender judge)

The asset spec below is checked exactly by `blendworks judge`:

```json
{
  "name": "standing torch",
  "format": "glb",
  "triangles": { "max": 600 },
  "size": { "x": [0.15, 0.35], "y": [0.15, 0.35], "z": [0.9, 1.1] },
  "origin": "bottom-centre",
  "manifold": true,
  "materials": { "min": 3, "max": 4 },
  "uv": { "required": true, "maxOverlap": 0.05 },
  "objects": { "max": 1 },
  "fileSize": { "maxBytes": 2000000 },
  "views": ["front", "left", "top", "three-quarter"],
  "brief": "A standing torch: wooden pole on a small base, iron cage near the top, a stylised emissive flame."
}
```

## Acceptance

1. `blendworks judge` passes every rule.
2. The judge views the contact sheet. The torch must match the look above, with a visibly glowing flame and a clear pole, base and cage.

## Deliver

- The `.glb` and the Blender Python script that builds it from an empty scene.
- Announce the `.glb`'s sha256 to the judge.
