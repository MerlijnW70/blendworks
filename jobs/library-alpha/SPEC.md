# Job: Foliage models from the library keep their cut-out masks

Poly Haven ships the cut-out mask of foliage models (grass, leaves) as a separate map (`Alpha`, `leaves_alpha`, and so on). The glTF it serves sets `alphaMode: BLEND` but points its base colour at a JPEG without an alpha channel and never references the mask. `library_download` fetches only the glTF and the files it includes, and `library_apply` only imports it. Every scanned plant therefore renders with its texture padding as solid dark blades: `grass_medium_01`, `island_tree_01` and `tree_small_02` all render black-leaved in Cycles. Make the library deliver and wire these masks so a downloaded plant renders as it does on Poly Haven.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Download:** a model download also fetches every mask map the files listing offers at the requested resolution (lossless format preferred), md5-checked and all-or-nothing like the other files, and records it in `LICENSE.json`. A mask that is listed badly or missing at that resolution does not fail the download; the result says which mask was skipped and why.
2. **Already downloaded:** a model downloaded before this change, without its masks, is not reported as complete: a new `library_download` fetches only the missing masks, and `library_apply` on it says the masks are missing and how to get them.
3. **Wiring:** `library_apply` on a model wires each mask into the Alpha of every imported material whose base colour image is the one the mask belongs to (matched by file, not by the glTF image name), sharing that texture's UV input, in non-colour data. The bridge does this in a general, documented way that also serves models imported outside the library. The result lists each mask with the materials it was wired into, and every mask it could not place.
4. **Rendering:** cut-out materials render correctly in Cycles and EEVEE: where the mask is black the background shows through, where it is white the base colour shows, with no dark fringe from the padding colour.
5. **Docs and MCP:** the library and import reference, and the tool descriptions where they change, through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: an offline download of a model whose listing has masks (fixtures, as the existing library tests do) gets the mask files and their record; a listing with a bad mask entry still downloads and reports it; an old record without masks is completed; a small rendered model with a base colour JPEG and a separate mask shows the background through the masked area and the base colour elsewhere (pixel checks at a small size, CPU, few samples); a mask whose base colour image is not in the model is reported, not silently dropped. No wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image).
- **Allowed files:** `src/mcp/library/**`, the bridge import command and a new bridge module for masks, `test/library-*`, `test/fixtures/polyhaven/**`, `bridge/tests/**`, `src/mcp/routing/**` data, `bench/tool-selection/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge downloads and applies `grass_medium_01` and `island_tree_01` at 1k from the live library, renders them, and sees cut-out blades and leaves instead of dark cards.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
