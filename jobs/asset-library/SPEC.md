# Job: A Poly Haven asset library for agents

Agents should be able to start from real CC0 material instead of inventing everything: HDRIs for lighting, scanned PBR textures, and reference models. Add a Poly Haven library to the MCP server, with search, preview and verified download into the workspace, and with licence records.

## Required

1. **Client:** `src/mcp/library/` holds a Poly Haven API client for `https://api.polyhaven.com` (`/assets`, `/info/<id>`, `/files/<id>`, `/categories/<type>`).
   - It sends a descriptive `User-Agent`, as Poly Haven asks of API users.
   - Every response is validated with zod, and a request fails cleanly on unexpected shapes.
   - It has timeouts, bounded retries with backoff, and a cache of listings on disk in the workspace with an expiry time.
   - Network access happens only in this client, on the Node side. The Blender side never downloads.
2. **Tools** (MCP tools, named `library_*`, separate from the bridge's `blender_*` tools):
   - `library_search`: by type (hdri, texture, model), free text, category and tags, with paging. It returns id, name, type, categories, dimensions and available resolutions.
   - `library_preview`: returns the asset's thumbnail as MCP image content, fetched through the client and capped in size.
   - `library_download`: downloads one asset at a chosen resolution and format into `<workspace>/library/<type>/<id>/`.
     - It checks each file against the md5 the API publishes and refuses a mismatch.
     - It writes all-or-nothing through a temporary folder, enforces a size cap (configurable, with a default suited to 2K and 4K textures), and refuses resolutions above the cap.
     - It writes `LICENSE.json` with the asset id, source URL, licence (CC0), authors and download time.
     - For models it fetches the glTF with its textures. For textures it fetches the PBR map set. For HDRIs it fetches one HDR or EXR file.
   - `library_apply`: uses the existing bridge commands only. It imports a model, builds a PBR material from a downloaded texture set (with `material_pbr` once the textures job has landed; until then it fails with a clear message), or sets a downloaded HDRI as the world environment. For the HDRI, add a minimal `set_world_hdri` bridge command in `bridge/blendworks_bridge/commands/lights.py`, using the workspace path rules.
3. **Safety:**
   - Only Poly Haven hosts are fetched (`api.polyhaven.com`, `dl.polyhaven.org`, `cdn.polyhaven.com`), and redirects elsewhere are refused.
   - Paths stay inside the workspace, and ids are validated against a strict pattern, with no path traversal.
   - Downloads never run code. Model files are only imported through the bridge's existing import path.
4. **Offline behaviour:** with no network, search fails with a clear message, and already downloaded assets remain usable.
5. **Docs:** a section "Asset library" in `docs/DESIGN.md` covers the tools, the folder layout, licence records and limits. The MCP instructions mention when to use the library (lighting, real materials, reference).

## Tests

All tests run without network: an injected fetch replays fixture responses in `test/fixtures/polyhaven/`, captured from the real API shapes and kept small.
- **Search:** paging and filtering.
- **Schema refusals:** a response with an unexpected shape is refused.
- **Checksums:** an md5 mismatch is refused, and nothing is left in the workspace.
- **Atomic downloads:** an interrupted download leaves nothing behind.
- **Host and path refusals:** a redirect to a foreign host, path traversal in an id, and a resolution above the cap are each refused.
- **Licence records:** `LICENSE.json` is written with the expected content.
- **Bridge:** `set_world_hdri` is tested in headless Blender with a tiny generated HDR.
- **Live smoke test:** optional, skipped unless `BLENDWORKS_LIVE=1`. It searches for one HDRI and downloads it at 1K.

## Rules

- Follow `CONTRIBUTING.md`. Runtime dependencies stay `@modelcontextprotocol/sdk` and `zod`, so use Node's own `fetch` and `crypto`.
- Touch only `src/mcp/library/` (new), the tool registration in `src/mcp/server.ts` and `src/mcp/tools.ts`, `src/mcp/instructions.ts`, `bridge/blendworks_bridge/commands/lights.py`, `bridge/tests/`, `test/` (new files only), and the new section of `docs/DESIGN.md`.
- The textures job runs in parallel and also edits `src/mcp/instructions.ts` and `docs/DESIGN.md`. Rebase onto the latest `main` before delivering, and keep both jobs' text.
- No quick fixes: each tool is complete, validated and tested as specified.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when the md5 check is removed, or when a redirect to a foreign host is followed.
3. The judge runs a live search and download of a 1K HDRI and a 1K texture set on the judge's machine, applies the HDRI, and views a render lit by it.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
