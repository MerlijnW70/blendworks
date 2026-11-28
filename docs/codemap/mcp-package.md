# Code map: MCP server and package build

src/mcp (server, routing, library), src/package and bridge/package (LODs, gltfpack), src/session.ts, src/blender.ts. Part of [the code map index](../CODEMAP.md).

One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (smoke, describe, crate, scene).

### bridge/package/ (11)

- `package_decimate`: Edge collapse decimation for LODs with locked borders. | fn: temporary_object discard_object + | test: package/
- `package_error`: Geometric error between LOD levels from directed distances. | fn: directed_distances geometric_error | test: package/
- `package_export`: Exports a LOD package as glb with its ancestors. | fn: with_ancestors export_glb | test: package/
- `package_levels`: LOD level checks and naming. | fn: LodError bounds_of + | test: package/
- `package_locks`: Vertices and edges that LOD decimation must keep: borders, material and UV seams. | fn: corner_arrays face_arrays + | test: package/
- `package_lods`: Entry point that builds the LOD package inside Blender. | fn: read_config uv_overlap + | test: package/
- `package_metrics`: Image metrics for LOD comparison: silhouette IoU and SSIM. | fn: silhouette silhouette_iou + | test: package/
- `package_plan`: LOD planning: screen error in pixels and switch distances. | fn: pixels_per_metre_at_one_metre screen_error_pixels + | test: package/
- `package_render`: Renders LOD levels for comparison. | fn: read_lods chosen_views + | test: package/
- `package_sheet`: Composes a LOD comparison sheet. | fn: opaque pixel_buffer + | test: package/
- `package_surface`: Surface distance queries for LOD error. | fn: mesh_surface triangle_soup + | test: package/

### src/ (2)

- `blender.ts`: Finds the Blender binary and the job count; the only place that does.
- `session.ts`: The headless Blender session: spawns Blender and speaks the bridge protocol.

### src/mcp/ (22)

- `boot.ts`: Boots the Blender session with backoff.
- `connection.ts`: The connection to Blender: progress, restarts and closing.
- `desktop.ts`: Connects to a desktop Blender add-on on a port.
- `errors.ts`: Turns argument and bridge errors into messages for the model.
- `failure-log.ts`: Counts failures and marks the session dead after too many.
- `headless.ts`: Starts the headless Blender session.
- `hygiene.ts`: Process guards of the MCP server.
- `index.ts`: The MCP server executable.
- `install-claude.ts`: Installs the server into Claude clients.
- `install.ts`: Plans the install of the server into an MCP client.
- `instructions.ts`: Builds the tiered server instructions within their size budget.
- `line-link.ts`: A line-delimited link to the Blender session.
- `options.ts`: Command line options of the server.
- `protocol.ts`: Types of the bridge request and reply.
- `recovery.ts`: Recovers the scene after a crash with the recover command.
- `results.ts`: Converts bridge results into MCP content with a size cap.
- `schema.ts`: Types and fallbacks of bridge command schemas on the MCP side.
- `server.ts`: Creates the MCP server and its parts.
- `start.ts`: Starts the server in headless or desktop mode.
- `surface.ts`: Builds the tool surface from the bridge commands.
- `tools.ts`: Registers one tool per bridge command, with timeouts and the run_python tool.
- `workspace.ts`: The workspace folder and its path checks.

### src/mcp/library/ (11)

- `apply.ts`: Applies a downloaded Poly Haven asset in the scene.
- `cache.ts`: Disk cache of library downloads.
- `client.ts`: Poly Haven API client.
- `common.ts`: Library constants: API host, license and folder.
- `http.ts`: HTTP helper with limits and retries.
- `index.ts`: The library object and its options.
- `plan.ts`: Plans which files of an asset to download.
- `schemas.ts`: Schemas of Poly Haven API replies.
- `search.ts`: Filters and pages the asset listing.
- `store.ts`: Stores downloaded assets with their license record.
- `tools.ts`: The library_search, library_preview, library_download and library_apply tools.

### src/mcp/routing/ (14)

- `bm25.ts`: BM25 ranking index.
- `catalog.ts`: Routing metadata of the tools: families, intents and nearest tools.
- `core.generated.ts`: Generated list of the core tool fill.
- `core.ts`: The core tool set: pinned tools and its size budget.
- `disclosure.ts`: Progressive disclosure: which tools are listed up front.
- `examples.ts`: Builds an example call from a tool's schema.
- `families.ts`: One-line descriptions of the tool families.
- `names.ts`: Names of the meta tools and the tool prefix.
- `router.ts`: The blender_find_tools and blender_call meta tools.
- `search.ts`: Tool search over the catalog with field weights.
- `synonyms.ts`: Synonym expansion for tool search.
- `text.ts`: Stemming and tokens for search.
- `validate.ts`: Checks call arguments against a tool's schema.
- `workflows.ts`: Named workflows (goals) and the tools they use.

### src/package/ (24)

- `analysis.ts`: Analyses a glb: boxes, matrices and texture slots.
- `blender-stages.ts`: The Blender stages of the package build: LODs and renders.
- `cli.ts`: The package command line.
- `compress.ts`: Compresses a glb with gltfpack.
- `equivalence.ts`: Checks that a packed glb equals its source within tolerances.
- `glb.ts`: Parses and builds glb files.
- `gltfpack-release.ts`: Pinned gltfpack releases per platform.
- `gltfpack.ts`: Runs the gltfpack WebAssembly build.
- `judge-stage.ts`: The package stage of the judge run.
- `ktx2.ts`: Reads KTX2 headers.
- `memory.ts`: Texture and GPU memory estimates.
- `native-install.ts`: Downloads and installs the native gltfpack.
- `native-run.ts`: Runs the native gltfpack.
- `native.ts`: Native gltfpack limits and facts.
- `pipeline.ts`: The package pipeline: inspect, LODs, compress and report.
- `report.ts`: Types of the package report.
- `rules.ts`: Package rules of the spec.
- `schemas.ts`: Schemas of the package measurements.
- `stage.ts`: Runs the package Blender scripts.
- `texture-check.ts`: Checks the textures of a package.
- `textures.ts`: Texture plans and KTX2 settings.
- `tiny.ts`: Builds a tiny textured glb for probes.
- `tool.ts`: Chooses between the npm and native gltfpack.
- `zip.ts`: Reads entries from zip files.
