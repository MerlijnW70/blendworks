# Blendworks — design

Blendworks lets AI agents build 3D assets in Blender and lets judges check those assets automatically. That makes 3D work something agents can be hired and paid for on Solive: a hirer posts an asset spec, a worker agent builds the asset with the Blender MCP server, and a judge runs the Blender judge against the spec and attests.

Three parts:

1. **The Blender bridge.** A command handler inside Blender (Python, `bpy`) that executes a fixed set of safe commands from JSON. It runs either inside a desktop Blender as an add-on, or as a headless Blender session the tools start themselves.
2. **The MCP server.** A Node/TypeScript stdio MCP server that exposes those commands as tools to Claude and other MCP hosts, including a render preview so the agent sees what it builds.
3. **The judge.** A command-line checker that opens a delivered asset in a sandboxed headless Blender with its own script, measures it against an asset spec, renders fixed views, and reports pass or fail.

Blender is 5.2 LTS:
- **On Windows:** `F:\tools\blender-5.2.3-windows-x64\blender.exe`.
- **In WSL:** `~/tools/blender/blender`.
The `BLENDER` environment variable names the binary everywhere.

## 1. The bridge protocol

- **Transport:** newline-delimited JSON over a localhost TCP socket (desktop add-on), or over the stdin and stdout of a headless Blender started with `--background --python bridge/session.py` (headless session).
- **Messages:**
  - request: `{ "id": n, "cmd": "<name>", "args": { … } }`;
  - reply: `{ "id": n, "ok": true, "result": { … } }` or `{ "id": n, "ok": false, "error": { "code": "...", "message": "..." } }`.
- **Errors:** every command validates its arguments and refuses unknown fields. A failing command never leaves the scene half-changed: it runs inside an undo step, or on a copy that is applied only on success.
- **Discovery:** `"cmd": "describe"` returns every command with its argument schema and a one-line description. The MCP server builds its tool list from it.
- **No arbitrary code by default.** `run_python` exists only when the session or add-on is started with `--allow-python`, and the MCP server marks the tool as dangerous.
- **Caps:** sizes and times are capped in `bridge/blendworks_bridge/limits.py`. Images are at most 8192 px per side. A bake is at most 4096 px and runs at most 600 s. It stops between channels once it passes its time limit (default 100 s), and the bake is then undone. The MCP server waits up to 660 s for a `bake` reply, so a bake at the cap still answers.
- **Bake device:** `bake` picks its device from `BLENDWORKS_DEVICE` as defined in section 4 (Render device); its `device` field overrides the variable for one call. The result names the device, the backend, any CPU fallback and the seconds per channel.
- **Texturing workflow:** model, then UV, then procedural or image materials, then bake, then export.
  - **UV:** `uv_smart_project` or `uv_unwrap`, with `uv_pack` for an atlas shared by several objects.
  - **Materials:** `material_procedural` and `material_layer`, or `material_pbr` from image maps.
  - **Bake:** `bake` with `rewire`, which gives the objects one `material_pbr` material made from the baked images.
  - **Export:** a `.glb` written by `export` carries every map: base colour, metallic-roughness, normal, emission and occlusion.
- **Colour spaces:** colour maps (base colour, emission) are sRGB, and data maps (metallic, roughness, ORM, normal, height, alpha, AO) are non-colour. Height is a bump in Blender only, because glTF has no height map. A bake folds it into the normal map.

### Command families

| Family | Commands (minimum) |
|---|---|
| Scene | `describe`, `scene_info` (objects, meshes with vertex, face and triangle counts, materials, cameras, lights, bounds, units), `new_scene`, `select`, `delete` |
| Objects | `add_primitive` (cube, cylinder, cone, sphere, ico sphere, torus, plane, with size and segments), `transform` (location, rotation, scale), `apply_transform`, `set_origin` (geometry centre, bottom centre, cursor), `duplicate`, `join`, `rename`, `parent` |
| Mesh editing | `extrude`, `inset`, `bevel` (by angle, by selected faces or by listed edges, optionally with harden normals), `subdivide`, `decimate`, `boolean` (union, difference, intersect, with one cutter or a list of cutters, optional manifold check), `mirror`, `array`, `solidify`, `shade_smooth` / `shade_flat`, `recalc_normals`, `merge_by_distance`, `apply_modifier` |
| Modifiers | `add_modifier` (typed fields for displace with built-in noise textures, weld, screw, curve, simple deform, wireframe, lattice, shrinkwrap, triangulate, weighted normal, bevel and solidify; unknown fields are refused), `apply_modifier` |
| Shapes from profiles | `lathe`, `sweep`, `loft`, `extrude_outline` (with holes), `gear`, `sprocket`, `roller_chain` |
| Repetition and placement | `instances` (linked copies at points, along waypoints, a curve or an edge loop, or on a circle; optionally realised into one mesh), `rivet_line` |
| Selection and queries | `mesh_query` (paged face centres, normals, areas, materials, islands), `transform_selection` (move, rotate, scale selected faces or vertices); face selectors on `extrude`, `inset`, `bevel`, `subdivide`, `shade_smooth`, `shade_flat`, `mesh_query`, `transform_selection` and `displace_noise` |
| Wear | `displace_noise` (seeded jitter or hammer-facet dents, masked by selection or vertex group) |
| Geometry from data | `mesh_from_data` (vertices and faces, with material indices, UVs, smooth flags, sharp edges and creases, inline or from a JSON file in the workspace, with one size cap), `curve_from_points`, `text_object` |
| Materials | `add_material` (Principled BSDF: base colour, metallic, roughness, emission, alpha), `assign_material` (whole object or face set), `vertex_colors` |
| Textures | `image_load` (PNG, JPEG, OpenEXR or WebP from the workspace, with a colour space), `image_new` (blank 8-bit or float image, a bake target), `image_save` (PNG or JPEG into the workspace, 8 or 16 bit, quality), `image_info` (size, colour space, file or packed, users) |
| PBR and procedural materials | `material_pbr` (Principled BSDF from image maps: base colour, metallic, roughness, ORM, normal in the OpenGL or DirectX convention, height as a bump, emission, alpha and AO; UV map and mapping), `material_procedural` (presets built in code: wood, worn metal, rust, stone, concrete, fabric, dirt; typed parameters), `material_layer` (an overlay preset over a material through a noise, edge, cavity or vertex colour mask) |
| Baking | `bake` (base colour, roughness, metallic and emission by emission, tangent-space normal and AO; margin, UV map, selected to active with a cage extrusion; optional rewire to a `material_pbr` material) |
| UV | `uv_smart_project` and `uv_unwrap` (island margin, texel density), `uv_pack` (margin, rotation, shared atlas across objects), `uv_info` (coverage, overlap, texel density) |
| Lights and camera | `add_light`, `add_camera`, `look_at`, `set_world` (colour or strength) |
| Output | `render_preview` (PNG of the current scene from the active or a named camera, or the standard turntable views, at a capped resolution, returned as base64), `export` (glTF binary `.glb`, FBX, OBJ), `save_blend` |
| Import | `import` (`.glb`, `.gltf`, `.fbx`, `.obj` from a path inside the working folder) |

All lengths are in metres, and all angles in degrees.

### Modelling kit

- **Shapes** (`lathe`, `sweep`, `loft`, `extrude_outline`, `gear`, `sprocket`, `roller_chain`) make real meshes with UVs and a `shading` choice: smooth, flat, or auto, which smooths everything except edges sharper than `smooth_angle`. A closed result is reported as `manifold` with its `volume`.
- **Lathe:**
  - The profile is `[x, z]` points in the XZ plane; `x` is the distance from the axis.
  - The first and last point may lie on the axis, and each such point is one vertex, so the result is closed and manifold.
  - `caps` closes an off-axis end with a flat face, or a partial turn with two wedge faces; `seam_merge` shares the vertices at the seam of a full turn.
- **Sweep:**
  - The profile moves along the path with rotation-minimising frames, which never flip.
  - A corner without `fillet_radius` is mitred, so the thickness stays constant; with it, the corner is a circular arc of that radius.
  - `scale_start` and `scale_end` taper the profile linearly with distance, and `twist` is the total roll in degrees.
  - A closed path spreads the frame drift over its length, so the seam has no gap; it needs `twist` in whole turns and equal scales.
  - A `curve` object is followed in world space.
- **Loft:** sections with fewer points get extra points by splitting their longest edges until they match the largest section (or `samples`), which keeps their shape. With `align`, each section's start point is shifted to the position that twists the skin least. The winding follows the direction of travel, whatever the section orientation.
- **UVs:**
  - The faces of a shape are unwrapped in metres: a sweep, loft or lathe is one strip along its length, and caps are flat islands.
  - The islands are then packed together into the UV square at one texel density, without overlap and without rotation.
  - A gear, plate or chain is unwrapped the same way, with its walls as one strip.
- **Instances:**
  - Linked copies share one mesh, named `name_000`, `name_001` and so on, under an empty named `name`. The source's mesh is used, not its transform.
  - A shared mesh cannot take `apply_modifier`; duplicate it unlinked first.
  - `realize` merges the copies into one mesh, which keeps the source's UVs, so the copies overlap in UV space.
  - Along a path, `spacing` places one at the start and then at each step that still fits; `count` spreads them over the whole path.
  - `align frame` turns X along the path or circle tangent and Z to the up or normal direction.
- **Booleans:** `cutters` are joined into one mesh and cut in a single exact operation, so overlapping cutters act as their union. After applying, close vertices are merged and the normals of a closed result are recalculated. `manifold` refuses, and rolls back, a result that is not a closed manifold.
- **Selection:** `faces`, `facing`, `box` (the world-space face centre lies inside), `with_material`, `normal` with `normal_angle`, `island` (connected faces, numbered by lowest face index) and `area_min` / `area_max` (world area) all combine with and.
- **Harden normals:** `bevel` with `harden_normals` stores custom normals: flat faces keep their own normal and the bevel faces blend into them. Blender stores custom normals with about four decimals.
- **Wear:** `displace_noise` never moves a vertex further than `amplitude`; the same `seed` gives the same result, and vertices at one position move together so seams stay closed.

## 2. The MCP server

- **Tools:** each bridge command becomes an MCP tool named `blender_<command>`, with its schema and a short, accurate description. Results that include images are returned as MCP image content.
- **Connection:** the server connects to a running desktop add-on when one is listening (`BLENDWORKS_PORT`, default 9876). Otherwise it starts and owns a headless session.
- **Workspace:** a working folder (`--workspace`) holds every import, export and save. Paths outside it are refused.
- **Install:** `node dist/mcp/index.js` is the server. `npm run install-claude` adds it to Claude Code (`claude mcp add`).

## 3. Asset specs

An asset spec is JSON (`schemas/asset-spec.schema.json`), so it can be pinned by sha256 in a Solive escrow. For example:

```json
{
  "name": "wooden crate",
  "format": "glb",
  "triangles": { "max": 800 },
  "size": { "x": [0.95, 1.05], "y": [0.95, 1.05], "z": [0.75, 0.85] },
  "origin": "bottom-centre",
  "manifold": true,
  "materials": { "min": 1, "max": 3 },
  "uv": { "required": true, "maxOverlap": 0.05 },
  "objects": { "max": 1 },
  "fileSize": { "maxBytes": 2000000 },
  "views": ["front", "back", "left", "right", "top", "three-quarter"],
  "brief": "A sturdy wooden crate with metal corner brackets, for a top-down game."
}
```

Three optional groups check textures, the glTF file itself and loose parts. For a textured asset:

```json
{
  "format": "glb",
  "textures": {
    "required": ["baseColor", "metallicRoughness", "normal"],
    "minSize": 512,
    "maxSize": 4096,
    "embedded": true,
    "maxCount": 3,
    "maxGpuBytes": 268435456,
    "powerOfTwo": true
  },
  "gltf": { "validator": { "maxErrors": 0, "maxWarnings": 10 } },
  "parts": { "maxFloating": 0, "tolerance": 0.001 }
}
```

- **`textures.required`:** the map kinds every material must have, from `baseColor`, `metallicRoughness`, `normal`, `emissive` and `occlusion`. Faces without a material count as a material, `(no material)`, that has none.
- **`textures.minSize` / `textures.maxSize`:** limits in pixels on the shorter and the longer side of every image. With no images, nothing breaks them.
- **`textures.embedded`:** when `true`, every image is inside the delivered file. An image read from a file beside it, or refused because it lies outside the asset folder, fails the rule.
- **`textures.maxCount`:** the most distinct images the materials may use.
- **`textures.maxGpuBytes`:** a budget for the estimated GPU memory of those images.
- **`textures.powerOfTwo`:** when `true`, both sides of every image are powers of two.
- **`gltf.validator`:** the most errors (`maxErrors`, 0 when left out) and warnings (`maxWarnings`, not checked when left out) the Khronos glTF-Validator may report. Only for `glb` and `gltf` specs.
- **`parts.maxFloating`:** the most loose parts that touch nothing, with `tolerance` in metres (0.001 when left out, at most 1).

The GPU estimate treats every image as uncompressed RGBA8 with a full mip chain, whatever its file format, so a compressed image counts by its decoded size. For an image of `w` × `h` pixels it is 4 bytes times the sum of `w_i × h_i` over the levels, where `w_0 = w`, `w_(i+1) = max(1, floor(w_i / 2))` (the same for `h`), and the chain ends at the first 1 × 1 level. A 4096 × 4096 image takes 4 × (4096² + 2048² + … + 1²) = 89,478,484 bytes. A 48 × 20 image takes 4 × (960 + 240 + 60 + 12 + 3 + 1) = 5,104 bytes.

## 4. The judge

`blendworks judge <spec.json> <asset> [--out <dir>] [--preview]` does the following:
1. Starts headless Blender in a sandbox with a fresh factory scene (`--factory-startup --disable-autoexec`). In WSL it also has no network.
2. Imports the asset with the judge's own script. The worker's file never runs code: a `.blend` delivery is opened with auto-run disabled, and only its data is read.
3. Measures every rule of the spec: triangles, bounds, origin, manifoldness, materials, UV coverage and overlap, object count, file size, textures and, when the spec asks, floating parts.
4. Renders the spec's views with a fixed camera rig fitted to the asset's bounds, a neutral three-point light, Cycles with a fixed seed, 24 samples and denoising, at 512 px. Outlines come from the compositor (edges in the normal and depth passes), so they cost almost nothing on any device. The result is a contact sheet.
5. Writes `report.json`, with every rule, its measured value and pass or fail, plus the PNGs. It exits 0 when every rule passes and 1 otherwise.

Before Blender starts, the judge runs the Khronos glTF-Validator on every `.glb` and `.gltf` delivery (see below).

### Textures

The judge reads every material's texture slots from the imported scene. It follows the links into the Principled BSDF's inputs, through any nodes, node groups and reroutes, and skips muted links and nodes:
- Base Color gives `baseColor`;
- Metallic and Roughness give `metallicRoughness`;
- Normal gives `normal`;
- Emission Color gives `emissive`;
- the Occlusion input of the glTF importer's `glTF Material Output` group gives `occlusion`.

Only materials on faces of the measured geometry count. For each distinct image, `measurements.textures.images` lists:
- its map kinds and the materials that use it;
- its size in pixels and its colour space;
- whether it is embedded, as its source: `packed` or `generated` are embedded, `file` is not, and then the file name is given too;
- its GPU estimate, and whether both sides are powers of two.

glTF files are imported without packing, so an image that is a file beside a `.gltf` stays external.

Base colour and emission must be in `sRGB`, and data maps in `Non-Color`. Each wrong pair is listed in `colourSpaceMismatches` and in the summary. It is a measurement, not a rule, so it does not decide pass or fail.

The contact sheet header always shows the texture count and the GPU estimate. `report.json` carries `measurements.textures` only when the spec has texture rules, and `measurements.floating` only when it has `parts`. A spec without the new rules gets exactly the report it got before.

### glTF validation

The validator is the official `gltf-validator` npm package. It runs in a worker thread of the judge's Node process, with a 2048 MB heap, the judge's timeout and a size cap of 128 MiB for the file and its resources together. The cap is `maxValidatorBytes` in the judge's options.

It may read only files in the asset's own folder: the resources of a `.gltf` beside it. It never opens a URI with a scheme (`http:`, `file:`, `data:` aside, which the validator decodes itself), an absolute path, or a path that leaves the folder. Each refused URI is listed and shows up as an `IO_ERROR` issue.

The full result goes to `validation.json` for every glTF delivery. With a `gltf.validator` rule, `report.json` also carries it as `validation`, listing every issue with its code, severity, JSON pointer and message, and the summary shows the counts and the first 10 issues. The rule compares the error and warning counts; infos and hints never count.

If the validator cannot finish (over the cap, a timeout, a crash), a spec with the rule fails at the `validate` stage. Without the rule the failure goes only to `validation.json`.

### Floating parts

A loose part is a connected piece of a mesh, after merging vertices closer than 1 µm, as for manifoldness. Each placed instance of a mesh counts on its own. A part is floating when its world-space bounds, grown by the tolerance on every side, overlap neither another part of its own object nor the bounds of another object. An asset of one part has nothing to touch, so it never floats.

`measurements.floating` lists each floating part by object and index, with its bounds. The parts of an object are numbered in order of their lowest corner (x, then y, then z).

### Render device

Every render picks its device from `BLENDWORKS_DEVICE`:
- **`auto`** (the default) tries OptiX, then CUDA, HIP, Metal and oneAPI inside the sandbox, and uses the first backend whose device lists and passes a small test render. Otherwise it renders on the CPU.
- **`gpu`** fails with a reason when no GPU backend works.
- **`cpu`** never starts a GPU.

The bridge's `bake` follows the same order and meaning, outside any sandbox. Its `auto` takes the first backend that lists a device. When a bake on it fails, `auto` bakes that channel again on the CPU and says so.

The denoiser is the OptiX denoiser on OptiX and OpenImageDenoise elsewhere. A re-run on the CPU gives byte-identical images. On a GPU, a small share of pixels may differ by one level out of 255.

`report.json` and the summary name the device, for example `render: gpu OPTIX (NVIDIA GeForce RTX 4080)` or `render: cpu`. They also give the wall time of each stage: measure, device (the GPU probe), render and sheet.

### Sandbox with a GPU

- **The address-space limit.** It stays on the measuring stage and on CPU renders. It is not used for GPU renders: CUDA reserves a large virtual address space, and under `prlimit --as` the GPU render of a large asset crashes.
- **GPU renders.** They run under `unshare -rn` with a data-segment limit (`prlimit --data`, and `RLIMIT_DATA` inside Blender) of the same size, plus the same timeout. The summary prints a separate `render sandbox:` line naming that limit.
- **No GPU in the sandbox.** If no GPU starts inside the sandbox, or Blender crashes there, `auto` renders on the CPU under the original limits. The summary says why.
- **Windows.** A job object caps memory for both devices.

### Preview mode

With `--preview`, the judge measures and checks every rule and draws the UV layout, but renders no views. The report marks the views as skipped (`renders.viewsSkipped`), and the exit code depends on the rules alone.

### Close-ups

`blendworks closeups <asset> --out <dir> [--res <px>] [--samples <n>]` renders 9 close-ups:
- a hero three-quarter view;
- a 2 × 2 grid of zoomed tiles from the front-right;
- a 2 × 2 grid of zoomed tiles from the back-left.

Each framing is fitted to the asset's vertices, and the four tiles of a grid together make up the whole view. The command also writes a labelled `closeup-sheet.png`. It uses the judge's light rig, device choice and sandbox, without outlines. The defaults are 1200 px and 16 samples with denoising, and the command prints its total time.

Its use with Solive is `intent-engine judge … --sandbox none --run "blendworks judge spec.json work.glb"`. Visual quality beyond the rules is for a judge agent viewing the contact sheet and the close-up sheet against the brief, or a committee.

## 5. Determinism

- Measurements are exact and repeatable.
- Renders use a fixed seed, samples and resolution, so the same asset on the same device gives the same report and the same images (byte-identical on the CPU; on a GPU, at most one level out of 255 apart in a small share of pixels).
- The judge pins the Blender version and refuses others.

## 6. Asset library

The MCP server offers Poly Haven's free CC0 assets as a starting point: HDRIs for lighting, scanned PBR texture sets for real materials, and models for reference. The `library_` tools sit beside the `blender_` tools.

| Tool | What it does |
|---|---|
| `library_search` | Searches by type (`hdri`, `texture`, `model`), free text, category and tags, with paging (`page`, `per_page` up to 24). It returns id, name, type, categories, tags, dimensions in metres, maximum pixel size and the resolutions on offer, most downloaded first. An unknown category is refused with the known ones. |
| `library_preview` | Returns the asset's thumbnail as PNG image content, 64 to 512 px, at most 1 MiB. |
| `library_download` | Downloads one asset at a chosen resolution and format into the workspace. An HDRI is one `.hdr` (default) or `.exr`. A texture is its PBR map set in `jpg` (default), `png` or `exr`: by default `Diffuse`, `nor_gl`, `Rough`, `Metal`, `AO`, `Displacement` and `Mask` where present, or the maps named in `maps`. A model is its `.gltf` with the buffers and textures it uses. |
| `library_apply` | Uses a downloaded asset through bridge commands only. An HDRI becomes the world environment with `set_world_hdri` (strength, rotation about Z). A model is imported with `import`. A texture set becomes a material with `material_pbr` and, given `object`, is assigned with `assign_material`; without `material_pbr` it fails with a clear message. |

`set_world_hdri` (bridge, Lights and camera family) loads an `.hdr` or `.exr` from inside the workspace, under the same path rules as `import`, into a new world: Environment Texture through a Mapping node to the Background.

### Folder layout and licence records

```
<workspace>/library/
  hdri/<id>/<id>_1k.hdr, LICENSE.json
  texture/<id>/<id>_diff_1k.jpg, <id>_nor_gl_1k.jpg, …, LICENSE.json
  model/<id>/<id>_1k.gltf, <id>.bin, textures/…, LICENSE.json
  .cache/   API listings, kept 24 hours
  .tmp/     downloads in progress
```

`LICENSE.json` records the asset id, name, type, source page (`https://polyhaven.com/a/<id>`), licence (`CC0-1.0` with its URL), authors, resolution, format, main file or maps, every file with its URL, size and md5, and the download time. It is also the manifest that `library_apply` and repeat downloads check.

### Limits and safety

- **Network:** only the Node side fetches, through one client, and only from `api.polyhaven.com`, `dl.polyhaven.org` and `cdn.polyhaven.com` over https. Redirects are followed by hand, at most 5, and one to any other host is refused. Requests carry a descriptive `User-Agent`, time out after 20 s without data, and are retried twice with exponential backoff on network errors, HTTP 429 and 5xx.
- **Validation:** every API response is checked with zod; an unexpected shape is refused.
- **Ids and paths:** ids match `^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$`. Every file path from the API must stay inside the asset folder, and every folder inside the workspace. A glTF may refer only to the files Poly Haven lists for it.
- **Downloads:** each file must have the published size and md5, or the download is refused. Files land in a temporary folder that replaces the asset folder only when everything has arrived, so a failure leaves nothing behind and keeps an earlier download intact. The total is capped at 300 MB by default (`BLENDWORKS_LIBRARY_MAX_MB`), which takes 2K and 4K texture sets; a larger resolution is refused before any file is fetched, naming the ones that fit.
- **No code:** downloads are data only. Models enter Blender only through the bridge's `import`.
- **Offline:** search, preview and new downloads need the network and fail with a clear message without it; cached listings answer for 24 hours. Downloaded assets keep working: `library_apply` and repeat downloads read only the workspace.
