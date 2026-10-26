# Asset job: a realistic pickaxe

Build a photorealistic, game-ready pickaxe in Blender and deliver it as a binary glTF (`.glb`) with baked PBR textures. Realism is the point of this job: it should look like a photographed, much-used miner's tool, not a stylised game prop.

## Look

A real miner's pickaxe standing upright on the end of its handle, head at the top.
- **Head:** a forged steel head with a pointed pick on one side and a flat chisel blade on the other. It curves gently downward and tapers to the ends, with a thicker eye in the middle where the handle passes through. Forged faces are slightly uneven and edges are softly rounded. The tips are sharpened bright metal where they have been ground.
- **Handle:** a hickory handle, oval in section, that swells towards the head and has a knob at the bottom end. It passes through the eye and sticks out a little above it, held by a wooden wedge and a small steel wedge visible in the top.
- **Wear:** dark forge scale and patchy rust on the head, polished steel along the working edges, and dings and scratches. The handle shows real wood grain, darkened and smoothed where hands grip it, with dirt near the bottom.

## Textures

Realism comes from baked image textures, not flat colours. The glTF exporter keeps image textures only, so bake procedural shading to images.
- Every material uses image textures: base colour, a roughness and metallic map, and a normal map.
- Each texture is at least 1024 px, and every image is embedded in the `.glb`.
- The steel uses metallic values; the wood does not.
- UVs are laid out without overlap, so that the baked textures map correctly.

## Rules (checked by the Blender judge)

The asset spec below is checked exactly by `blendworks judge`:

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
  "brief": "A photorealistic miner's pickaxe standing on its handle end: forged steel head with pick and chisel ends, rust and forge scale, ground bright edges; hickory handle with real grain, wedged eye, grip wear; baked PBR textures."
}
```

## Acceptance

1. `blendworks judge` passes every rule.
2. The judge views the contact sheet plus its own close-up renders of the head, the eye with its wedges, the tips and the handle grain.
3. It must read as a real tool: correct proportions for a real pickaxe, visible wood grain, metal that looks forged and worn, and textures with no stretching or visible seams on the main faces.
4. The judge checks the `.glb` itself: the images must be embedded, with base colour, roughness and metallic, and normal maps on every material.

## Deliver

- The `.glb` and the Blender Python script that builds it from an empty scene, including the texture bake.
- Announce the `.glb`'s sha256 to the judge.
