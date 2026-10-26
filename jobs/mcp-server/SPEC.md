# Job: The Blender MCP server

Build the MCP server of docs/DESIGN.md section 2 in `src/mcp/`, speaking the bridge protocol of section 1.

## Required

1. **Server:** a stdio MCP server (`@modelcontextprotocol/sdk`) that builds its tools from the bridge's `describe`:
   - each tool is named `blender_<command>`, with an input schema converted from the bridge schema and its description;
   - a `render_preview` result comes back as MCP image content (PNG) plus a short text;
   - `run_python` is offered only when the bridge has it, with a description that says it runs arbitrary code.
2. **Connection:**
   - it connects to a desktop add-on on `BLENDWORKS_PORT` (default 9876) when it answers `describe` within 1 s;
   - otherwise it starts its own headless session (`blender --background --factory-startup --python bridge/session.py -- --workspace <dir>`);
   - it restarts a crashed session once and reports the restart;
   - requests are serialized, each with a timeout.
3. **Workspace:** `--workspace <dir>` (default `./workspace`) is created if missing. Paths given by the client are resolved inside it and refused outside it.
4. **Server instructions:** a short text for the model saying:
   - work in metres;
   - check the result with `blender_render_preview` after each few steps;
   - use `blender_scene_info` to verify counts and sizes;
   - export the final asset with `blender_export`.
5. **Install:** `npm run install-claude` runs `claude mcp add --scope user blendworks -- node <abs path>/dist/mcp/index.js --workspace <dir>`. It explains itself and refuses if `claude` is missing.
6. **Tests:**
   - against a fake bridge (an in-process stub speaking the protocol): tool listing, schema conversion, image content, the `run_python` gating, workspace refusal, timeouts and the crash restart;
   - an end-to-end test with the real headless session after the bridge job lands (skipped with a clear reason only while `bridge/session.py` does not exist). An MCP client in the test lists the tools, builds a cube, renders a preview and exports a `.glb` into the workspace.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only `src/mcp/`, `test/mcp*` and `package.json` scripts.
- The bridge job builds `bridge/` and `src/session.ts` in parallel. Use its `startSession()` once it is on `main` (rebase before delivering), and do not duplicate it.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, with the end-to-end test running (not skipped) if the bridge has landed.
2. The judge adds the server to Claude Code and asks Claude to build a small crate. Claude sees previews and exports a `.glb`.
3. A test fails when the judge lets a client path escape the workspace.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
