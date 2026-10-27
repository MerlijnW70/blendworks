# Job: A session that never loses work, and tools that scale to big scenes

Agents building detailed assets lose their whole scene when a call times out. `run_python` rollback misses deleted objects and material changes. `scene_info` returns hundreds of kilobytes on a big scene, and previews cannot zoom in on a part. Make the session robust and the inspection tools scale. This must be done properly: every guarantee in `docs/DESIGN.md` must be true and tested.

## Required

1. **Checkpoints and recovery:**
   - Add `load_blend`, which opens a `.blend` from the workspace with auto-run off.
   - The session autosaves to `<workspace>/.blendworks/autosave.blend` after mutating commands. It saves at most once every N seconds, and always before slow commands (bake, boolean, export, `run_python`). Write atomically, through a temp file and a rename, and keep the previous autosave as a fallback.
   - When the owned headless session is restarted after a crash or timeout, the MCP server reloads the latest autosave. The next tool result tells the agent what happened and which state was restored.
   - Add `checkpoint` (a named save) and `restore_checkpoint`, and list checkpoints in `scene_info`.
2. **Timeouts:**
   - Every command has a default timeout, documented per command in `describe`. `run_python` is a slow command.
   - Every tool accepts an optional `timeout_seconds`, capped per command.
   - A timeout kills only the request, and the session recovers from the autosave as in item 1.
3. **Rollback that holds:**
   - A failing command leaves the scene exactly as before. This covers deleted objects, materials and their node trees, images, worlds, lights, cameras, curves, collections, modifiers and custom properties.
   - Use Blender's own undo (an undo push before the command, undo on failure, checked in background mode) or an equivalent full-data snapshot. Whichever you choose, prove it with tests.
   - Read-only commands take no snapshot.
   - The snapshot cost must not grow quadratically with the number of meshes.
4. **Scaling inspection:**
   - `scene_info` takes `detail` (summary, objects, full), `names` (glob), `limit` and `offset`. The default is totals plus at most 100 objects, with a note when more exist.
   - Bounds are computed with `foreach_get` and numpy, once per call.
   - The MCP server caps any text result at a documented size, telling the agent how to page.
5. **Better previews:**
   - `render_preview` uses the device choice of `docs/DESIGN.md` section 4. Reuse `bridge/blendworks_bridge/device.py`.
   - It accepts `focus` (an object name or a point, with width and direction) for close-ups.
   - It accepts `shading`: shaded, clay, wireframe overlay, normals, UV checker, or material ID colours.
   - It adds a `bottom` view, and an optional JPEG output for smaller results.
6. **Long calls:**
   - The MCP server sends progress notifications (`notifications/progress`, when the client gives a progress token) about every 10 s while a request runs.
   - It honours request cancellation: queued requests are dropped, and a running one is stopped by restarting the session and recovering as in item 1.
   - `close()` never hangs.
7. **Truthful tool metadata:**
   - `describe` reports `mutates`, `destructive` (delete, new scene, overwriting exports and the delete option of boolean) and the timeout.
   - The MCP annotations are derived from these fields, not from hard-coded lists in `src/mcp/tools.ts`.
8. **Export fidelity:** the default export includes the ancestors (empties) of exported objects, so the glTF hierarchy survives. A test proves it.
9. **Docs:** update `docs/DESIGN.md` sections 1 and 2 and the MCP instructions with the recovery behaviour, paging and preview options.

## Tests

- **Recovery:** a session killed in the middle of a command recovers the last autosave, and the agent is told so. A test fails if the autosave is removed.
- **Rollback:** after a failing `run_python` that deletes an object, edits a material, removes an image and adds a collection, the scene is identical. The test compares a full data fingerprint, not only names.
- **Snapshot cost:** with 2000 meshes, a no-op mutating command stays under a stated budget measured in the test. A read-only command takes no snapshot.
- **`scene_info` paging and the result cap:** totals, globs and offsets on a scene of 1500 objects.
- **Preview:** `focus` and each shading mode render non-empty images, and the device field is reported. The tests run on a machine without a GPU.
- **Progress and cancellation:** an MCP-level test receives progress and cancels a slow call.
- **Export:** a parent empty survives a default export.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only these files:
  - in the bridge: `bridge/blendworks_bridge/transaction.py`, `handler.py`, `registry.py`, `limits.py`, `util.py`, and `commands/` files `run_python.py`, `files.py`, `scene.py`, `render.py`;
  - new bridge modules;
  - `src/mcp/` except `library/`;
  - `src/session.ts`;
  - `bridge/tests/`, `test/`;
  - `docs/DESIGN.md` sections 1 and 2.
- You may update existing tests that assert behaviour this spec changes. List them in your report.
- The modeling-kit job edits other files in `bridge/blendworks_bridge/commands/` in parallel, and both jobs may add to `commands/__init__.py`. The dev-speed job edits `package.json`, `scripts/` and the test setup. Rebase onto the latest `main` before delivering.
- Keep the PC usable: one Blender process at a time, and run the full check at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when rollback stops restoring a deleted object, when recovery stops reloading the autosave, or when `scene_info` stops paging.
3. The judge runs a real session through the MCP server. It builds part of an asset, kills Blender in the middle of a `run_python` call, sees the scene recovered, renders a `focus` close-up in clay and wireframe, and views the images.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
