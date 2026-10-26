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

### Command families

| Family | Commands (minimum) |
|---|---|
| Scene | `describe`, `scene_info` (objects, meshes with vertex, face and triangle counts, materials, cameras, lights, bounds, units), `new_scene`, `select`, `delete` |
| Objects | `add_primitive` (cube, cylinder, cone, sphere, ico sphere, torus, plane, with size and segments), `transform` (location, rotation, scale), `apply_transform`, `set_origin` (geometry centre, bottom centre, cursor), `duplicate`, `join`, `rename`, `parent` |
| Mesh editing | `extrude`, `inset`, `bevel`, `subdivide`, `decimate`, `boolean` (union, difference, intersect), `mirror`, `array`, `solidify`, `shade_smooth` / `shade_flat`, `recalc_normals`, `merge_by_distance`, `apply_modifier` |
| Geometry from data | `mesh_from_data` (vertices and faces, with a size cap), `curve_from_points`, `text_object` |
| Materials | `add_material` (Principled BSDF: base colour, metallic, roughness, emission, alpha), `assign_material` (whole object or face set), `vertex_colors` |
| UV | `uv_smart_project`, `uv_unwrap`, `uv_info` (coverage, overlap) |
| Lights and camera | `add_light`, `add_camera`, `look_at`, `set_world` (colour or strength) |
| Output | `render_preview` (PNG of the current scene from the active or a named camera, or the standard turntable views, at a capped resolution, returned as base64), `export` (glTF binary `.glb`, FBX, OBJ), `save_blend` |
| Import | `import` (`.glb`, `.gltf`, `.fbx`, `.obj` from a path inside the working folder) |

All lengths are in metres, and all angles in degrees.

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

## 4. The judge

`blendworks judge <spec.json> <asset> [--out <dir>]` does the following:
1. Starts headless Blender in a sandbox with a fresh factory scene (`--factory-startup --disable-autoexec`). In WSL it also has no network.
2. Imports the asset with the judge's own script. The worker's file never runs code: a `.blend` delivery is opened with auto-run disabled, and only its data is read.
3. Measures every rule of the spec: triangles, bounds, origin, manifoldness, materials, UV coverage and overlap, object count, file size.
4. Renders the spec's views with a fixed camera rig fitted to the asset's bounds, a neutral three-point light, Cycles on the CPU, a fixed seed and fixed samples. The result is a contact sheet.
5. Writes `report.json`, with every rule, its measured value and pass or fail, plus the PNGs. It exits 0 when every rule passes and 1 otherwise.

Its use with Solive is `intent-engine judge … --sandbox none --run "blendworks judge spec.json work.glb"`. Visual quality beyond the rules is for a judge agent viewing the contact sheet against the brief, or a committee.

## 5. Determinism

- Measurements are exact and repeatable.
- Renders use a fixed seed, samples and resolution, so the same asset gives the same report and near-identical images.
- The judge pins the Blender version and refuses others.
