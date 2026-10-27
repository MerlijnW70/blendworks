# Asset job: an antique armillary sphere

Build a beautiful, museum-quality antique armillary sphere in Blender and deliver it as a binary glTF (`.glb`) with baked PBR textures. This is a showcase piece, so it should look like a photographed antique scientific instrument.

## Look

A brass armillary sphere on a turned wooden stand with a marble base, standing upright.
- **Rings:** nested brass rings for the meridian, horizon, equator, ecliptic, both tropics and both polar circles. Each ring has a rectangular, slightly bevelled section.
  - The meridian and horizon rings carry fine engraved degree ticks, with longer ticks every 10°.
  - The ecliptic band is wider and shows the twelve zodiac sector divisions.
  - Rings join with small pins and collars.
  - The sphere is tilted on its polar axis at about 23.5° to the horizon ring.
- **Centre:** a small globe or sun sphere on the polar axis, with end caps and finials at both poles.
- **Stand:** a turned walnut column with beads and coves (a lathe profile), on a round, moulded marble or stone base. The horizon ring sits on four curved brass supports.
- **Materials:** aged brass with darker patina in recesses and polished high points; dark walnut with visible grain; veined marble.
  - Bake procedural detail into image textures (base colour, roughness/metallic, normal).
  - The engraving may be partly in geometry and partly in the normal map, but it must read in close-ups.
- Every part touches the structure, with nothing floating. Triangles go into visible shape.

## Rules (checked by the Blender judge)

```json
{
  "name": "antique armillary sphere",
  "format": "glb",
  "triangles": { "min": 30000, "max": 150000, "minVisible": 25000 },
  "size": { "x": [0.3, 0.5], "y": [0.3, 0.5], "z": [0.45, 0.7] },
  "origin": "bottom-centre",
  "manifold": true,
  "faces": { "maxDegenerate": 0, "maxDuplicate": 0, "maxHiddenRatio": 0.3 },
  "materials": { "min": 3, "max": 8 },
  "uv": { "required": true, "maxOverlap": 0.02, "minCoverage": 0.4 },
  "objects": { "min": 1, "max": 40 },
  "fileSize": { "maxBytes": 25000000 },
  "textures": {
    "required": ["baseColor", "metallicRoughness", "normal"],
    "minSize": 1024,
    "maxSize": 4096,
    "embedded": true,
    "maxCount": 9,
    "powerOfTwo": true
  },
  "gltf": { "validator": { "maxErrors": 0, "maxWarnings": 0 } },
  "parts": { "maxFloating": 0, "tolerance": 0.001 },
  "views": ["front", "left", "top", "three-quarter"],
  "brief": "A museum-quality antique armillary sphere: nested engraved brass rings tilted at 23.5 degrees, central globe and pole finials, turned walnut column, moulded marble base; aged brass with patina, walnut grain, veined marble, baked PBR textures."
}
```

## Acceptance

1. `blendworks judge` passes every rule.
2. The judge views the contact sheet and `blendworks closeups`. It must read as a real antique instrument: correct ring structure and tilt, engraving visible up close, convincing brass, wood and marble.

## Deliver

- The `.glb` and the script or command log that builds it from an empty scene.
- Announce the `.glb`'s sha256 to the judge.
