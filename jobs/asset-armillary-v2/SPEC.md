# Asset job: the antique armillary sphere, complete, built with Blendworks tools only

Rebuild the antique armillary sphere (`jobs/asset-armillary`) as the definitive showcase of the current Blendworks toolset.

The first version has three gaps:
- its ticks have no numerals;
- its ecliptic band shows no zodiac signs;
- its marble reads as crazed rather than veined.

It also needed raw bpy for slivers, marble and export. Since then Blendworks has gained:
- `engrave` with zodiac and planet glyphs;
- the `marble` and `brass` presets;
- `clean_mesh`, export with tangents, and analytic circle paths for sweeps;
- coverage-aware UV packing and per-material bake sizes;
- `material_nodes`, empties and collections;
- the visual judge, and LOD and KTX2 packaging.

## Look

As in `jobs/asset-armillary/SPEC.md`, plus the following:
- **Meridian and horizon rings:** degree numerals every 10° (0 to 350, or 0 to 90 per quadrant on the meridian, as a real instrument has), engraved and legible in close-ups.
- **Ecliptic band:** the twelve zodiac signs, each in its own sector, and the month names or initials on the horizon ring if they fit.
- **Brass:** aged brass, with patina in the engravings and recesses, polished high points and fine directional scratches. No crack-like patterns.
- **Marble base:** veined marble, with flowing veins, not cracks.
- **Hierarchy:** a clean object hierarchy (named empties or collections for the sphere, the stand and the base) that survives export.

## Rules

The spec below is checked by `blendworks judge`, including the visual judge through the claude-code provider:

```json
{
  "name": "antique armillary sphere v2",
  "format": "glb",
  "triangles": { "min": 60000, "max": 250000, "minVisible": 50000 },
  "size": { "x": [0.3, 0.5], "y": [0.3, 0.5], "z": [0.45, 0.7] },
  "origin": "bottom-centre",
  "manifold": true,
  "faces": { "maxDegenerate": 0, "maxDuplicate": 0, "maxHiddenRatio": 0.3 },
  "materials": { "min": 3, "max": 8 },
  "uv": { "required": true, "maxOverlap": 0.02, "minCoverage": 0.45 },
  "objects": { "min": 1, "max": 60 },
  "fileSize": { "maxBytes": 25000000 },
  "textures": {
    "required": ["baseColor", "metallicRoughness", "normal"],
    "minSize": 512,
    "maxSize": 4096,
    "embedded": true,
    "maxCount": 12,
    "powerOfTwo": true
  },
  "gltf": { "validator": { "maxErrors": 0, "maxWarnings": 0 } },
  "parts": { "maxFloating": 0, "tolerance": 0.001 },
  "views": ["front", "left", "top", "three-quarter"],
  "visual": {
    "rubric": [
      { "id": "matches-brief", "question": "Is this a convincing antique brass armillary sphere on a turned wooden stand with a veined marble base?", "weight": 2 },
      { "id": "engraving", "question": "Are degree numerals and zodiac signs engraved on the rings and legible in the close-ups?", "weight": 2 },
      { "id": "materials", "question": "Do the materials read as aged brass with patina, walnut with grain, and veined marble, without crack-like artefacts?", "weight": 1 }
    ],
    "minScore": 0.75,
    "samples": 3,
    "required": true
  },
  "lods": { "count": 2, "ratios": [0.5, 0.25], "minSilhouetteIoU": 0.95 },
  "package": { "meshopt": true, "ktx2": true },
  "brief": "A museum-quality antique armillary sphere: nested engraved brass rings with degree numerals and zodiac signs, tilted at 23.5 degrees, central globe and pole finials, turned walnut column, veined marble base; aged brass with patina; baked PBR textures."
}
```

## Acceptance

1. `blendworks judge` passes every rule, the required visual rule included.
2. The build uses Blendworks commands only, through the bridge Handler or the MCP server, with no `run_python` and no raw `bpy` or `bmesh` in the build script beyond driving commands. List any gap that forced otherwise; that list is the product feedback.
3. The judge views the close-ups: legible numerals and signs, veined marble, beautiful brass.

## Deliver

- The `.glb`, plus the build script or command log that rebuilds it from an empty scene.
- Announce the `.glb`'s sha256 to the judge.
