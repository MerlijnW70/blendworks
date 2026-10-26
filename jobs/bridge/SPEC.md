# Job: The Blender bridge

Build the command handler of docs/DESIGN.md section 1. It runs inside Blender (Python and `bpy`) as a headless session over stdin and stdout, and as a desktop add-on over a localhost socket.

## Required

1. **Shared handler.** `bridge/blendworks_bridge/` is one Python package used by both transports. It provides:
   - **a command registry** where each command declares an argument schema: types, ranges, required and optional fields, and no unknown fields;
   - **`describe`**, which returns every command with its schema and a one-line description;
   - **every command family in the design's table**, with metres and degrees.
   Each command runs atomically (an undo step, or work on a copy applied only on success) and returns a structured result. Errors use codes: `bad_args`, `not_found`, `failed`, `forbidden`.
2. **Headless session.** `bridge/session.py` is started with `blender --background --factory-startup --python bridge/session.py -- [--workspace DIR] [--allow-python]`. It reads one JSON request per line from stdin and writes one reply per line to stdout. Blender's own log output goes to stderr, never to stdout. It exits cleanly on EOF or a `quit` command.
3. **Desktop add-on.** `bridge/addon/` is an installable Blender add-on (a zip built by `npm run build:addon`). It serves the same handler on `127.0.0.1:<port>` (default 9876, settable in its preferences). It runs requests on Blender's main thread through a timer queue, never from the socket thread, and has a start/stop toggle in the sidebar.
4. **Safety:**
   - every file path must be inside the workspace;
   - imports accept only `.glb`, `.gltf`, `.fbx` and `.obj`;
   - `run_python` exists only with `--allow-python`;
   - the size caps (vertices in `mesh_from_data`, render resolution, preview samples) are enforced.
5. **`render_preview`:**
   - Cycles on the CPU (EEVEE where a GPU exists in the desktop add-on) at capped resolution and samples, with a fixed seed;
   - the views: the active camera, a named camera, or the standard turntable views (front, back, left, right, top, three-quarter) with a camera fitted to the scene's bounds;
   - returns a base64 PNG per view.
6. **Tests** (`bridge/tests/test_*.py`, run inside headless Blender by `npm run test:bridge`):
   - every command, on its success and refusal paths;
   - atomicity: a failing boolean leaves the scene unchanged;
   - the workspace path refusal;
   - `run_python` gated;
   - `describe` matching the registry;
   - a round trip of building a simple crate (cube, bevel, inset, extrude, material, UV, origin at bottom centre), exported to `.glb`, re-imported, with the same triangle count and bounds.

   A vitest test (`test/session.test.ts`) starts the headless session through `src/` (a small `startSession()` in `src/session.ts` that speaks the protocol) and runs `describe`, `add_primitive`, `scene_info` and `render_preview`, checking the PNG header.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only `bridge/`, `src/session.ts`, `test/session*`, and `package.json` scripts (`build:addon`, and add the bridge tests to `check`).
- Other jobs build the MCP server (`src/mcp/`) and the judge (`src/judge/`, `bridge/judge/`) in parallel against the protocol in docs/DESIGN.md. Keep to it exactly, and rebase onto the latest main before delivering.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, with `BLENDER` pointing at Blender 5.2.
2. A test fails when the judge lets a path outside the workspace through, or makes `run_python` available without the flag.
3. The judge installs the add-on in a desktop Blender and drives it over the socket.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
