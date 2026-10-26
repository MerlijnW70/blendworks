# Asset job: a wooden crate

Build a game-ready 3D wooden crate in Blender and deliver it as a binary glTF (`.glb`).

## Look

A sturdy wooden crate for a top-down pixel-art underground game:
- visible planks with gaps or grooves between them;
- a frame of thicker boards along the edges;
- dark metal brackets on the corners;
- a few nail or rivet details.
It should read clearly from above and from a three-quarter view. Use a warm wood colour with darker wood for the frame, and dark grey metal. Materials are plain colours (Principled BSDF base colour, roughness and metallic); no image textures are needed.

## Rules (checked by the Blender judge)

The asset spec below is checked exactly by `blendworks judge`:

```json
{
  "name": "wooden crate",
  "format": "glb",
  "triangles": { "max": 800 },
  "size": { "x": [0.95, 1.05], "y": [0.95, 1.05], "z": [0.75, 0.85] },
  "origin": "bottom-centre",
  "manifold": true,
  "materials": { "min": 2, "max": 3 },
  "uv": { "required": true, "maxOverlap": 0.05 },
  "objects": { "max": 1 },
  "fileSize": { "maxBytes": 2000000 },
  "views": ["front", "back", "left", "right", "top", "three-quarter"],
  "brief": "A sturdy wooden crate with planks, a thicker frame and dark metal corner brackets, for a top-down game."
}
```

## Acceptance

1. `blendworks judge` passes every rule.
2. The judge views the contact sheet. The crate must match the look above: planks, frame, brackets, clean silhouette and sensible colours. A plain box with a texture-less material does not pass.

## Deliver

- The `.glb` and the Blender Python script that builds it from an empty scene.
- Announce the `.glb`'s sha256 to the judge.
