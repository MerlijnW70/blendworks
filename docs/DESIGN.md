# Blendworks â€” design

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
  - request: `{ "id": n, "cmd": "<name>", "args": { â€¦ } }`;
  - reply: `{ "id": n, "ok": true, "result": { â€¦ } }` or `{ "id": n, "ok": false, "error": { "code": "...", "message": "..." } }`.
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

`blendworks judge <spec.json> <asset> [--out <dir>] [--preview]` does the following:
1. Starts headless Blender in a sandbox with a fresh factory scene (`--factory-startup --disable-autoexec`). In WSL it also has no network.
2. Imports the asset with the judge's own script. The worker's file never runs code: a `.blend` delivery is opened with auto-run disabled, and only its data is read.
3. Measures every rule of the spec: triangles, bounds, origin, manifoldness, materials, UV coverage and overlap, object count, file size.
4. Renders the spec's views with a fixed camera rig fitted to the asset's bounds, a neutral three-point light, Cycles with a fixed seed, 24 samples and denoising, at 512 px. Outlines come from the compositor (edges in the normal and depth passes), so they cost almost nothing on any device. The result is a contact sheet.
5. Writes `report.json`, with every rule, its measured value and pass or fail, plus the PNGs. It exits 0 when every rule passes and 1 otherwise.

### Render device

Every render picks its device from `BLENDWORKS_DEVICE`:
- **`auto`** (the default) tries OptiX, then CUDA, HIP, Metal and oneAPI inside the sandbox, and uses the first backend whose device lists and passes a small test render. Otherwise it renders on the CPU.
- **`gpu`** fails with a reason when no GPU backend works.
- **`cpu`** never starts a GPU.

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
  texture/<id>/<id>_diff_1k.jpg, <id>_nor_gl_1k.jpg, â€¦, LICENSE.json
  model/<id>/<id>_1k.gltf, <id>.bin, textures/â€¦, LICENSE.json
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
