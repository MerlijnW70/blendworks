# Job: Textures, PBR materials and baking as bridge commands

Agents can make flat Principled materials but nothing with textures. A realistic asset therefore needs `run_python`, which is the gated escape hatch and not a workflow. Add proper bridge commands for image textures, PBR map wiring, procedural materials and baking. The MCP server picks them up from `describe` as `blender_` tools.

## Required

1. **Images:**
   - `image_load` loads a PNG, JPEG, EXR or WebP from inside the workspace (the same path rules as `import`) as a named image, and reports its size, channels and colour space.
   - `image_new` creates a blank image with a name, size, colour, alpha and 32-bit float option, for use as a bake target.
   - `image_save` writes an image into the workspace as PNG or JPEG, with quality and bit depth.
   - `image_info` lists images with their size, colour space, packed or file state and users.
   - Sizes are capped through `limits.py`, at 8192 px per side by default.
2. **PBR material from maps:** `material_pbr` builds a Principled BSDF material from named images or workspace paths.
   - Accepted maps: base colour, metallic, roughness, a combined ORM map (channel order selectable), normal (OpenGL or DirectX convention, with strength), height or displacement as a bump (strength and distance), emission (with strength), alpha, and ambient occlusion where the glTF exporter supports it.
   - Each map gets the correct colour space (sRGB for colour and emission, non-colour for data).
   - It accepts a UV map name and a mapping (scale, offset, rotation).
   - It results in a material that the glTF exporter writes with every map. A test re-imports the `.glb` and checks this.
3. **Procedural materials:** `material_procedural` creates bakeable procedural materials from a fixed, documented set of presets, for example wood, worn metal, rust, stone, concrete, fabric and dirt overlay.
   - Each preset has typed parameters: colours, scale, seed, wear amount, grain direction and so on.
   - The presets are node graphs built in code, not arbitrary node input, so no code execution is possible.
   - `material_layer` blends an overlay preset over an existing material by a mask: noise, edge wear from the geometry pointiness or an AO approximation, cavity, or a vertex colour.
4. **Baking:** `bake` bakes an object's or a selection's material channels into images.
   - Channels: base colour, roughness, metallic, normal (tangent space), emission and AO. Colour, roughness, metallic and emission are baked by emission, with sample counts per channel.
   - It supports a margin, a target UV map and a selected-to-active bake (high to low poly) with a cage extrusion.
   - It optionally rewires the material to the baked images with `material_pbr`, so the result exports to glTF.
   - Device: GPU when one is usable (OptiX, then CUDA, HIP, Metal and oneAPI), else the CPU, following the `BLENDWORKS_DEVICE` semantics in `docs/DESIGN.md`. If the speed job's device helper is on `main` when you rebase, reuse it instead of duplicating it.
   - It reports the device used, the time per channel and the output image names.
   - Bakes have a time and size cap in `limits.py`, and a cancelled or failed bake leaves no half-wired material.
5. **UV for texturing:** extend `uv_smart_project` and `uv_unwrap` with island margin and texel-density options, and add `uv_pack` (margin, rotation, and a shared atlas across several objects). `uv_info` reports texel density.
6. **Transactions:** every new command follows the protocol in `docs/DESIGN.md` section 1. It validates its arguments, refuses unknown fields, and on failure leaves the scene unchanged.
7. **Docs:** add the texture, material and bake families to the command table in `docs/DESIGN.md`, and to the MCP server's instructions where they guide the workflow. That workflow is: model, then UV, then procedural or image materials, then bake, then export.

## Tests (`bridge/tests/` and `test/`)

1. **PBR round trip:** `material_pbr` with all maps on a cube is exported to `.glb` and re-imported. The base colour, metallic-roughness, normal and emission textures are present, with the right colour spaces.
2. **Bake values:** a known procedural colour baked by emission gives the expected pixel values, within a tolerance worked out by hand. A tangent-space normal bake of a flat plane gives (0.5, 0.5, 1.0).
3. **Selected-to-active:** a bevelled high-poly cube baked onto a low-poly cube produces a non-flat normal map at the edges.
4. **Refusals:** paths outside the workspace, oversize images, unknown map names and unknown preset parameters are refused, and the scene is left unchanged.
5. **Device choice:** `BLENDWORKS_DEVICE=cpu` forces the CPU. `auto` falls back to the CPU with a stubbed empty device list. The tests pass on a machine without a GPU.
6. **Visual check:** an end-to-end test builds a small textured prop (for example a wooden plank with a worn iron band) from presets, bakes it at 1024 px, exports it, and renders a preview. The judge looks at that preview.

## Rules

- Follow `CONTRIBUTING.md`: no comments, at most 400 lines per file, and only `bpy`, `bmesh`, `mathutils` and the standard library on the Blender side.
- Touch only `bridge/blendworks_bridge/`, `bridge/tests/`, `test/` (new files only), `src/mcp/instructions.ts`, and section 1 and the command table of `docs/DESIGN.md`. Do not touch `src/judge/` or `bridge/judge/`.
- No quick fixes: each command is complete, validated and tested as specified. Rebase onto the latest `main` before delivering.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when a map is written with the wrong colour space, or when a failed bake leaves the material changed.
3. The judge drives the new tools through the MCP server on the RTX 4080 machine and gets a correctly textured `.glb`. The judge views the end-to-end preview and a re-import of the exported asset.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Include the preview path and the bake timings (device, per channel) in the report. Announce its sha256 to the judge.
