# Asset job: fix the realistic pickaxe to pass the full judge

The paid pickaxe (`jobs/asset-pickaxe`) passed the judge of its time. The extended judge (texture rules, Khronos glTF-Validator) finds two real defects: zero-length tangent vectors (`ACCESSOR_VECTOR3_NON_UNIT` at `/meshes/2/primitives/1/attributes/TANGENT`, the wedges). The review also noted that the top of the wooden wedge renders too pale and grey. Fix the asset at its source. Do not edit the `.glb` by hand.

## Starting point

The build script `artifacts/proof/pickaxe-build.py` on the judge's machine (`F:\blendworks\artifacts\proof\`), and the delivered `pickaxe.glb` next to it.

## Required

- Find the cause of the zero-length tangents: degenerate UVs on the wedge faces, zero-area triangles, or tangent export without valid UVs. Fix the geometry or UVs so that valid tangents can be exported. Do not merely switch tangent export off, unless you show that the normal maps still render correctly without exported tangents and explain why that is the better asset.
- Make the wooden wedge's end grain read as dark, slightly dirty hickory or ash end grain, consistent with the handle top.
- Keep everything else of the approved asset: shape, proportions, textures and look. Changes must be limited to the defects.

## Rules (checked by the Blender judge)

```json
{
  "name": "realistic pickaxe",
  "format": "glb",
  "triangles": { "min": 8000, "max": 60000 },
  "size": { "x": [0.45, 0.65], "y": [0.04, 0.12], "z": [0.85, 1.0] },
  "origin": "bottom-centre",
  "manifold": true,
  "materials": { "min": 2, "max": 5 },
  "uv": { "required": true, "maxOverlap": 0.02, "minCoverage": 0.5 },
  "objects": { "min": 1, "max": 4 },
  "fileSize": { "maxBytes": 25000000 },
  "views": ["front", "left", "top", "three-quarter"],
  "brief": "A photorealistic miner's pickaxe standing on its handle end: forged steel head with pick and chisel ends, rust and forge scale, ground bright edges; hickory handle with real grain, wedged eye, grip wear; baked PBR textures.",
  "textures": {
    "required": ["baseColor", "metallicRoughness", "normal"],
    "minSize": 1024,
    "maxSize": 4096,
    "embedded": true,
    "maxCount": 3,
    "maxGpuBytes": 268435456,
    "powerOfTwo": true
  },
  "gltf": { "validator": { "maxErrors": 0, "maxWarnings": 0 } },
  "parts": { "maxFloating": 0, "tolerance": 0.001 }
}
```

## Acceptance

1. `blendworks judge` (main with the judge-QA job) passes every rule, with 0 validator errors and 0 warnings.
2. `blendworks closeups` of the fixed asset shows the wedge end grain dark and natural, and the rest unchanged next to the approved close-ups.

## Deliver

- The fixed `.glb` and the updated build script, which rebuilds it from an empty scene.
- A short note on the cause and the fix.
- Announce the `.glb`'s sha256 to the judge.
