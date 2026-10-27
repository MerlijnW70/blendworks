# Blendworks — design

Blendworks lets AI agents build 3D assets in Blender and lets judges check those assets automatically. That makes 3D work something agents can be hired and paid for on Solive: a hirer posts an asset spec, a worker agent builds the asset with the Blender MCP server, and a judge runs the Blender judge against the spec and attests.

Three parts:

1. **The Blender bridge.** A command handler inside Blender (Python, `bpy`) that executes a fixed set of safe commands from JSON. It runs either inside a desktop Blender as an add-on, or as a headless Blender session the tools start themselves.
2. **The MCP server.** A Node/TypeScript stdio MCP server that exposes those commands as tools to Claude and other MCP hosts, including a render preview so the agent sees what it builds.
3. **The judge.** A command-line checker that opens a delivered asset in a sandboxed headless Blender with its own script, measures it against an asset spec, renders fixed views, and reports pass or fail.

Blender is 5.2 LTS ([download](https://www.blender.org/download/lts/)). `src/blender.ts` is the one place that finds it, for the server, the judge, the scripts and the tests:
- **`BLENDER`:** the environment variable names the binary. When it is set it is used, and an error says so if the file is missing.
- **Standard locations:** otherwise the first that exists. On Windows, `Program Files\Blender Foundation\Blender 5.2\blender.exe`, the same under `%LOCALAPPDATA%\Programs`, and `~\tools\blender\blender.exe`. On Linux and WSL, `~/tools/blender/blender`, `~/blender/blender`, `/opt/blender/blender` and the system folders. On macOS, `/Applications/Blender.app`.
- **`PATH`:** last, a `blender` on the path.

The error for a missing Blender lists the places it looked and the download link. `npm run doctor` reports what it finds and checks that the version is 5.2. `BLENDWORKS_JOBS` (default 2) caps how many Blender processes run at once in tests and scripts.

## 1. The bridge protocol

- **Transport:** newline-delimited JSON over a localhost TCP socket (desktop add-on), or over the stdin and stdout of a headless Blender started with `--background --python bridge/session.py` (headless session).
- **Messages:**
  - request: `{ "id": n, "cmd": "<name>", "args": { … } }`;
  - reply: `{ "id": n, "ok": true, "result": { … } }` or `{ "id": n, "ok": false, "error": { "code": "...", "message": "..." } }`.
- **Errors:** every command validates its arguments and refuses unknown fields. A failing command never leaves the scene half-changed.
- **Rollback:** before a mutating command the bridge pushes a step on Blender's own undo stack (memory undo, which also works in background mode). When the command fails, it pushes the failed state and undoes back to that step. This restores every data-block, including deleted ones: objects, meshes, materials and their node trees, images, worlds, lights, cameras, curves, collections, modifiers and custom properties.
  - Unsaved image pixels are not part of undo. Images that a failing command made dirty are reloaded. `run_python` also keeps a copy of the pixels of images that are already dirty, up to 1 GiB, or it refuses to run.
  - Read-only commands take no snapshot. A snapshot costs time in proportion to the data that changed, not to the number of meshes.
  - The desktop add-on also pushes a named undo step after each successful command. It needs global undo with at least 2 steps, and refuses mutating commands otherwise.
- **Discovery:** `"cmd": "describe"` returns every command with its argument schema, a one-line description and its metadata. The MCP server builds its tool list from it.
  - `mutates`: it changes the scene. `writes_files`: it writes into the workspace.
  - `destructive`: it can discard work that rollback cannot bring back (`delete`, `new_scene`, `load_blend`, `restore_checkpoint`, `run_python`). A command that is destructive only in some cases adds `destructive_when`: `export`, `save_blend`, `image_save` and `checkpoint` when they overwrite a file, and `boolean` when `cutter_action` is delete.
  - `slow`, `timeout` and `max_timeout`: the default and the largest timeout in seconds. Most commands default to 120 s and allow 600 s. Slow commands default to 300 s and allow 1800 s: `run_python`, `export`, `import`, `save_blend`, `load_blend`, `checkpoint`, `restore_checkpoint`, `render_preview`, `boolean`, `decimate`, `apply_modifier`, `uv_pack`, `set_world_hdri`, `mesh_from_data`, `sweep`, `loft`, `instances`, `rivet_line`, `roller_chain` and `displace_noise`. `bake` defaults to 660 s and allows 1200 s.
  - `internal`: not offered as an MCP tool (`describe`, `recover`).
- **Autosave (headless session):** after a mutating command the session saves the whole scene to `<workspace>/.blendworks/autosave.blend`, at most once every `BLENDWORKS_AUTOSAVE_SECONDS` (default 30; `off` disables it). When there are unsaved changes, it always saves before a slow command.
  - Each save is written to a temporary file and renamed into place. The previous save is kept as `autosave.prev.blend`. `autosave.json` records the time, the reason (for example `before run_python`) and the object count.
  - `scene_info` reports the autosave state. The desktop add-on does not autosave; Blender's own autosave and undo cover it.
- **Recovery:** the internal `recover` command opens the newest readable autosave, or else the previous one, and reports which file it loaded, with its time and reason.
- **Files and checkpoints:** `load_blend` opens a `.blend` from the workspace in place of the scene, with auto-run off, so the file's scripts and Python drivers never run. `checkpoint` saves a named copy in `.blendworks/checkpoints/` (at most 64), and `restore_checkpoint` opens one. Both opening commands update the autosave. In the desktop add-on they refuse to drop unsaved changes unless `discard_unsaved` is true.
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
| Scene | `describe`, `scene_info` (totals, a page of objects with vertex, face and triangle counts and bounds, materials, cameras, lights, units, checkpoints), `new_scene`, `select`, `delete`, `checkpoint`, `restore_checkpoint` |
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
| Output | `render_preview` (PNG or JPEG from the active or a named camera, the turntable views plus `bottom`, or a close-up `focus`, in a chosen shading, at a capped resolution, returned as base64), `export` (glTF binary `.glb`, FBX, OBJ, with the parent empties of the exported objects), `save_blend` |
| Import | `import` (`.glb`, `.gltf`, `.fbx`, `.obj` from a path inside the working folder), `load_blend` |

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

### Inspecting big scenes

- `scene_info` takes `detail`:
  - `summary`: totals, bounds and name lists;
  - `objects` (the default): plus a page of objects;
  - `full`: plus each object's data, collections, custom properties, vertex groups and shape keys, and the settings of the materials those objects use.
- The page is sorted by name. `names` filters it with a case-sensitive glob, `limit` sets its size (default 100, at most 1000) and `offset` skips objects. `page` gives `matched` and `next_offset`, and `notes` says when more objects exist. Totals always cover the whole scene. The name lists of materials, cameras and lights stop at 100, with a note.
- Bounds are exact over the evaluated vertices. They are computed with `foreach_get` and numpy, once per object per call.

### Previews

- **Device:** `render_preview` renders with Cycles on the device chosen as in section 4, from `BLENDWORKS_DEVICE` or its own `device` field. Its `auto` takes the first GPU backend that lists a device. If the render fails there, it renders again on the CPU and says so. The result names the device (`device`, `device_label`).
- **Close-ups:** `focus` frames an `object` (its bounds centre and size) or a `point`, with a `width` in metres visible at the focus. It looks from `focus.direction`, or from each of `views` (default three-quarter).
- **Shading:**
  - `shaded`: the scene's materials;
  - `clay`: one grey material;
  - `wireframe`: clay with every mesh edge drawn as a line about one pixel wide, at most 400 000 edges;
  - `normals`: world-space normals as colours;
  - `uv_checker`: a colour grid on the active UV map, and the result lists meshes without UVs;
  - `material_id`: one flat colour per material, with the legend in `material_colors`.
- **Output:** PNG, or JPEG with `format` jpeg and a `quality` (default 85). The scene is left exactly as it was.

## 2. The MCP server

- **Tools:** each bridge command becomes an MCP tool named `blender_<command>`, with its schema and a short, accurate description. Results that include images are returned as MCP image content.
- **Connection:** the server connects to a running desktop add-on when one is listening (`BLENDWORKS_PORT`, default 9876). Otherwise it starts and owns a headless session.
- **Annotations:** each tool's `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint` come from the command's `describe` metadata.
  - A command that changes nothing and writes no file is read-only and idempotent.
  - `destructive` sets the destructive hint, and only `run_python` is open-world.
  - Internal commands are not tools.
- **Requests** run one at a time, in order.
  - **Timeouts:** every tool takes an optional `timeout_seconds`, up to the command's `max_timeout`. The default is the command's `timeout`, and `--timeout` sets one default for all. A timeout stops only that request: the owned session is killed, restarted and recovered as below, and the queued requests then run on the new session. A desktop Blender is never killed; the server reconnects to it.
  - **Progress:** when a call carries a progress token, the server sends `notifications/progress` about every 10 s while the request waits or runs. `progress` counts seconds, and the message says whether the request is queued or running and when it times out.
  - **Cancellation:** a cancelled request that is still queued is dropped before it reaches Blender. A running one is stopped by restarting the owned session and recovering it.
  - **Close:** `close()` drops the queue, stops the running request and stops Blender within a few seconds. It never hangs.
- **Recovery:** when the owned session crashes, times out, is cancelled or is found stopped, the server starts a fresh session and calls `recover`.
  - The tool result says what happened and which state was restored, for example `Reloaded .blendworks/autosave.blend saved at 2026-10-27T12:00:00Z (before run_python); the scene has 12 objects.` Without an autosave, it says that the scene is empty.
  - If reloading fails or crashes Blender again, the server starts one empty session and says so. A session that cannot start at all is not restarted in a loop.
- **Result size:** a text result is cut at 64 000 characters. The cut ends with a note on how to ask for less, for example with the paging fields of `scene_info`. Images do not count.
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

### Units and axes

All lengths are metres. glTF, FBX and OBJ deliveries are read as metres by their importers. A `.blend` delivery is converted through its scene's `unit_settings.scale_length`: 100 units at a scale of 0.01 measure 1 m, and the origin is scaled with them.

The judge measures in Blender's axes: Z is up, -Y is the front, X is the right. A glTF file is Y-up, and its importer maps glTF +Y to Blender +Z and glTF +Z to Blender -Y. Sizes, bounds and points in `report.json` are always in Blender axes.

A hirer who thinks in glTF axes sets `"upAxis": "y"`. Then the spec's `size.y` is the height (Blender Z), `size.z` is the depth (Blender Y), and a point `[x, y, z]` in an `origin` rule means the Blender point `[x, -z, y]`. Without `upAxis`, or with `"z"`, the spec uses Blender axes.

### Rules that resist gaming

The measurements behind these rules come from faces only: a vertex or edge that belongs to no face never moves the bounds, the size or the origin. For example:

```json
{
  "format": "glb",
  "triangles": { "min": 8000, "max": 60000, "minVisible": 7000 },
  "size": { "minExtent": 0.85, "maxExtent": 1.0 },
  "manifold": { "required": true, "noInverted": true },
  "faces": { "maxDegenerate": 0, "maxDuplicate": 0, "maxHiddenRatio": 0.15 },
  "shells": { "max": 6 },
  "selfContained": true,
  "renders": { "required": true }
}
```

| Rule | Passes when | Prevents |
|---|---|---|
| `manifold: true` (or `{ "required": true }`) | no boundary, non-manifold or wire edges, no non-manifold or loose vertices | holes, fins, and stray points or wires hidden in the file |
| `manifold.noInverted` (`{ "noInverted": true }`) | no closed shell has a negative signed volume | a mesh turned inside out, which is closed and manifold but renders dark and breaks booleans and physics |
| `triangles.minVisible` | at least this many triangles are visible from outside | meeting `triangles.min` with hidden filler |
| `faces.maxHiddenRatio` | at most this share of the surface area is never visible from outside | padding with interior faces, and texture space spent on surfaces nobody sees |
| `faces.maxDegenerate` | at most this many faces have an area of at most 1 µm² (the weld distance squared) | zero-area padding, which adds triangles and breaks tangents and normals |
| `faces.maxDuplicate` | at most this many faces repeat the vertex positions of another face | stacked copies of a face, which add triangles, flicker (z-fighting) and break manifoldness |
| `shells.max` | the asset has at most this many shells | crumbs and specks scattered over or inside the model |
| `size.minExtent` / `size.maxExtent` | the longest side is at least / at most this many metres | an asset of the right shape at the wrong scale, whatever its orientation |
| `origin` as `{ "point": [x, y, z], "tolerance": t }` | the origin (pivot) lies within `t` metres of the point | a pivot away from where the game expects it |
| `selfContained` | every file the delivery refers to is in the delivery | a texture or material file that exists only on the worker's machine |
| `renders.required` | the views rendered | a verdict without visual evidence, when the hirer wants one |

How they are measured:
- **Shells** are connected pieces of faces after welding vertices closer than 1 µm. A shell is closed when every edge has exactly two faces with consistent winding. Its signed volume is the sum of `v0 · (v1 × v2) / 6` over its triangles in the mesh's own space, so a mirrored object (negative scale) is not inverted. A volume within `1e-9 × extent³` of zero counts as flat, not inverted. Every placed instance counts its shells.
- **Visible from outside** uses a BVH of every face in world space. From each face the judge casts rays from its triangle centroids and three inner points of its largest triangle, in 64 directions: a Fibonacci sphere turned by a fixed seeded rotation, tried in order of how far they point along the face normal. A face is visible when one ray escapes. Degenerate faces are never visible. With more than 20,000 faces, a fixed seeded sample of 20,000 faces is tested and the counts are scaled up; `faces.tested` and `faces.sampled` say so. `faces.hiddenRatio` is the hidden share of the tested area.
- **Duplicate faces** compare the sorted vertex positions of every non-degenerate face in world space, rounded to 1 µm, across all objects. The glTF importer already drops a face that repeats the vertices of another, so duplicates come mostly in `.blend`, FBX and OBJ files.

### UV coverage and overlap

UVs outside the unit square are reported as `uv.outsideUnitSquare`: the share of the mapped surface area whose faces have a UV corner outside 0–1. For coverage and overlap the UVs are wrapped into the unit square, as a texture with the glTF default `REPEAT` sampling reads them: a face at u = 1.3 covers the same texels as one at u = 0.3. UDIM tiles are wrapped the same way, so faces in different tiles at the same place overlap; glTF cannot carry a set of separate UDIM images.

Coverage is weighted by 3D surface area. Each face may cover the UV square only up to its share of the surface: a face with 10 % of the area counts for at most 0.1 of the square, so a face over that counts each of its texels with the weight `(face area / surface area) / (face UV area)`. Where faces overlap, a texel counts once, with the largest weight. A layout with an even texel density and a total UV area of at most 1 is unchanged by the weighting, but a tiny or hidden face blown up to fill the square no longer buys coverage. Faces with no 3D area are ignored. Coverage is quantised to 1/255 per texel.

Shared mesh data is counted once for UV and topology: four wheels that share one mesh fill the UV square once and do not overlap. Triangles, objects, shells, bounds and visibility count every placed instance.

### Per-object rules

`objects.named` checks objects matched by a name pattern, where `*` matches any run of characters and `?` one character:

```json
"objects": {
  "max": 6,
  "named": [
    { "name": "Wheel.*", "required": true, "triangles": { "max": 2000 }, "size": { "maxExtent": 0.7 }, "origin": "centre", "materials": { "max": 1 } },
    { "name": "Body", "origin": { "point": [0, 0, 0.3], "tolerance": 0.005 } }
  ]
}
```

`required` passes when at least one object matches. Every other rule applies to each matching object on its own, with the object's world-space faces for its size and its own origin as its pivot. A rule reports the number of matches and the first ten objects that break it. The objects are listed in `measurements.objectList` only when the spec names objects.

## 4. The judge

`blendworks judge <spec.json> <asset> [--out <dir>] [--preview] [--render-timeout <s>]` does the following:
1. **Private copy.** Copies the delivery into a private temporary folder and judges only that copy. The delivery is the asset plus the files it refers to inside its folder: the buffers and images of a glTF, the material libraries of an OBJ and the textures they name, and the textures of an FBX. A `.blend` is copied alone. The report lists each file with its size and sha256, and the sha256 of the set (`asset.setSha256`: the sha256 of the lines `<sha256>  <path>`, sorted by path). `fileSize` counts every file of the set. A reference that is not in the folder is listed in `measurements.references.unresolved` and fails `selfContained`.
2. **Validation.** Runs the Khronos glTF-Validator on every `.glb` and `.gltf` delivery (see below).
3. **Measurement.** Starts headless Blender in the sandbox with a fresh factory scene (`--factory-startup --disable-autoexec`) and imports the copy with the judge's own script. The worker's file never runs code: a `.blend` delivery is opened with auto-run disabled, and only its data is read. Before Blender evaluates anything, the importer limits below refuse what could exhaust memory. The scene is evaluated at frame 1, the frame the render uses too, so the frame an animated asset was saved on does not matter; an armature is measured in its pose at frame 1. Then every rule of the spec is measured.
4. **Verdict.** The rules decide pass or fail from the measurements and the validation alone.
5. **Evidence.** Renders the spec's views with a fixed camera rig fitted to the asset's bounds, a neutral three-point light, Cycles with a fixed seed, 24 samples and denoising, at 512 px. Outlines come from the compositor (edges in the normal and depth passes), so they cost almost nothing on any device. The result is a contact sheet.
6. **Report.** Writes `report.json` with every rule, its measured value and pass or fail, plus the PNGs and the sha256 of each. It exits 0 when every rule passes and 1 otherwise.

### Renders are evidence

A render that fails, crashes or runs out of time is reported in `renders` (`status` `failed`, with the failure) and in the summary, and the verdict stands. The judge then still draws a contact sheet with the header and the UV layout, without views. A spec with `"renders": { "required": true }` adds the rule `renders.required`, which fails unless the views rendered.

Render cost is bounded before rendering starts, not only by the clock: at most 2,000,000 triangles (`renderMaxTriangles` in the judge's options) and at most 64 Mi sample-pixels (views × 512² × 24 samples). Over the budget the views are skipped with the reason (`status` `skipped`), and the verdict stands. `--render-timeout` sets the render stage's own timeout (the judge's `--timeout` when left out). Two judges on machines of different speed give the same verdict for the same asset and spec: a slower machine can only lose evidence.

Close-ups have their own budget: 9 × resolution² × samples at most 1.5 G sample-pixels; a request over it is refused before Blender starts.

### Importer limits

- **glTF.** Before import, the judge reads the glTF JSON. It adds up the triangles the accessors declare (the indices, or the positions without indices, of triangle lists, strips and fans) for every node that places a mesh, through the whole node hierarchy and `EXT_mesh_gpu_instancing`. Over the triangle cap it refuses the file with `too_many_triangles`. It reads every image's size from its header (PNG, JPEG, WebP, KTX2) and refuses an image over 16,384 pixels on a side, or over 256 Mi pixels for all images together, with `image_too_large`. Draco (`KHR_draco_mesh_compression`) is allowed: its accessors declare the decoded counts, which are checked like any other, and the decoded mesh is counted again after import. A file that requires meshopt (`EXT_meshopt_compression`) is refused with `unsupported_extension`, because Blender's importer cannot decode it; a file that only uses it, with an uncompressed fallback, is read through the fallback.
- **Modifiers and instances.** Before evaluation, the judge bounds the triangles each object can make from its mesh, curve, text, surface or metaball data, its modifiers (subdivision, array, mirror, screw, solidify, bevel, triangulate, edge split, wireframe, skin, explode and boolean grow it; deform modifiers keep it; decimate, mask, build and weld shrink it), and its collection, vertex, face and particle instances, nested up to 16 levels. Over the triangle cap the asset fails with `too_many_triangles` before anything runs. Geometry nodes, fluid, remesh, ocean, mesh-sequence caches, volume-to-mesh and any modifier the judge does not know cannot be bounded, and fail with `unbounded_geometry`: apply them before delivery. After evaluation the triangles are counted again against the cap.

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

The contact sheet header always shows the texture count and the GPU estimate. `report.json` carries `measurements.textures` only when the spec has texture rules, and `measurements.floating` only when it has `parts`.

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
- **GPU renders.** They run in the same namespaces (see Isolation) with a data-segment limit (`prlimit --data`, and `RLIMIT_DATA` inside Blender) of the same size, plus the same timeout. The summary prints a separate `render sandbox:` line naming that limit.
- **No GPU in the sandbox.** If no GPU starts inside the sandbox, or Blender crashes there, `auto` renders on the CPU under the original limits. The summary says why.
- **Windows.** A job object caps memory for both devices.

### Isolation

The summary's `sandbox:` line names every mechanism in use, and says plainly when one is missing.

- **Linux and WSL.** When `unshare` can create user namespaces, Blender runs in its own user, mount, PID and network namespaces (`unshare --user --map-root-user --mount --pid --fork --kill-child --net`). A small script, `bridge/judge/sandbox.sh`, builds a new root on a tmpfs. `/usr`, `/bin`, `/sbin`, `/lib*`, `/etc` and `/sys`, the Blender folder, the judge's scripts and the delivery copy are bound read-only. The stage's output folder is the only writable folder besides a fresh `/tmp` and `/dev/shm`. `/dev` holds only `null`, `zero`, `full`, `random`, `urandom` and `tty`, plus the GPU devices for a GPU render. The script then calls `pivot_root` and detaches the old root, so the home folder, the original delivery and every other file are not there at all, and `/proc` shows only the sandbox's own processes. The memory limit (`prlimit`) and the timeout apply as before. Without user namespaces the judge falls back to `unshare -rn` (no network only) or to nothing, and the summary says `files not isolated`. The script needs only `util-linux`, so the judge does not depend on `bwrap`.
- **Windows.** Blender runs at low integrity, started by `bridge/judge/low_integrity.py` with Blender's own Python: a copy of the user's token without privileges, lowered to the low mandatory level, in a job object that kills Blender when the judge stops it. Only the stage's output folder, labelled low with `icacls`, is writable, so a judged asset cannot change any other file. Reads are not limited: a low-integrity process can read what the user can, and the network is not isolated. The job object inside Blender caps memory and forbids child processes as before. If Blender's Python is missing or the token cannot be lowered, Blender runs at the user's integrity and the summary says why. An AppContainer would also limit reads, but it needs access rules on the Blender folder and on the GPU driver, which the judge cannot set without changing the machine, so it is not used.

Blender gets the thread cap of `BLENDWORKS_JOBS` (the CPU count divided by it, 2 when unset), as everywhere else in Blendworks.

### Comparing reports

`blendworks diff <reportA.json> <reportB.json> [--json]` compares two reports for revision rounds and disputes: the verdict, the input hashes (spec, asset and delivery set), every rule with its measured value and limit, every measurement down to its leaves, and the sha256 of each rendered view and of the contact sheet. It exits 0 when they match, 1 when they differ and 2 when a file is not a report.

### Preview mode

With `--preview`, the judge measures and checks every rule and draws the UV layout, but renders no views. The report marks the views as skipped (`renders.viewsSkipped`, `renders.status` `preview`), and the exit code depends on the rules alone, as it always does.

### Close-ups

`blendworks closeups <asset> --out <dir> [--res <px>] [--samples <n>]` renders 9 close-ups:
- a hero three-quarter view;
- a 2 × 2 grid of zoomed tiles from the front-right;
- a 2 × 2 grid of zoomed tiles from the back-left.

Each framing is fitted to the asset's vertices, and the four tiles of a grid together make up the whole view. The command also writes a labelled `closeup-sheet.png`. It uses the judge's light rig, device choice, private copy and sandbox, without outlines. The defaults are 1200 px and 16 samples with denoising, and the command prints its total time.

Its use with Solive is `intent-engine judge … --sandbox none --run "blendworks judge spec.json work.glb"`. Visual quality beyond the rules is for a judge agent viewing the contact sheet and the close-up sheet against the brief, or a committee.

## 5. Determinism

- Measurements are exact and repeatable. The visibility estimate uses fixed directions and a fixed seed, so it is repeatable too, and it never depends on time.
- The verdict depends on the measurements only, never on whether or how fast the views render, so judges on fast and slow machines agree.
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
