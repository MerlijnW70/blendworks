# Job: Polish round 2 — the seven gaps the armillary builder hit

The agent that built the antique armillary sphere with Blendworks tools still had to drop to raw bpy, or leave things out, for seven reasons. It reported them precisely. Close each gap with a proper, validated, transactional bridge command, tested with values worked out by hand where possible. Its build script (`artifacts/proof/armillary-build.py` on the judge's machine) shows the workarounds; read it as evidence of the need, not as code to copy.

## Base

- **Base commit:** `055f843`. Rebase onto the latest `main` before delivering.

## Required

1. **Engraving text and symbols onto a surface:**
   - `engrave` cuts or embosses a string into a mesh, following a surface: a planar face region, a cylinder or ring band (text wrapped around an axis), or a curve path. Use Blender's bundled font or a font file in the workspace.
   - It accepts `size`, `depth` (cut) or `height` (emboss), `spacing`, `align`, `rotation` and `offset` along the path.
   - It accepts a repeat pattern for scales, for example a number every 10° around a ring.
   - Add a small built-in symbol set, at least the twelve zodiac signs and the planet symbols, as clean vector outlines. Do not rely on a system font.
   - The result is manifold, with no degenerate faces, and the operation is one transaction.
   - **Test:** engraving "10" on a ring removes the expected volume within tolerance, keeps the mesh manifold, and leaves 0 degenerate faces.
2. **Veined marble:** add a `marble` procedural preset, and a `veins` option for `stone`.
   - Use banded, ridged veins with domain warping, and typed parameters: vein colour, vein width, turbulence, scale, seed and base colours.
   - Keep the existing voronoi cracks as their own option.
   - **Test:** a baked sample has vein-like structure: elongated high-contrast bands, checked with a simple directional statistic that is deterministic for a seed. The judge views a rendered swatch.
3. **Mesh cleanup after booleans:**
   - Add `clean_mesh`. It dissolves degenerate and zero-area faces, splits or fan-retriangulates polygons that tessellate into slivers, merges collinear vertices on straight edges where safe, removes loose geometry, and recalculates normals.
   - It reports counts for each fix, and keeps the mesh manifold when its input was manifold.
   - `boolean` gets a `clean` option that runs this after the cut, on by default. It replaces the current merge-and-normals-only cleanup.
   - **Test:** a box cut by many coplanar overlapping cutters (the armillary tick case) leaves degenerate faces before and 0 after, and stays manifold.
4. **Export options:** `export` gains the following, all documented, with defaults that pass the glTF validator:
   - `tangents` (on by default for meshes with normal maps);
   - image format (auto, PNG or JPEG, with JPEG quality);
   - `apply_modifiers`, `include_hidden`, `draco` off or on, and `yup`.
   **Test:** a textured export with default options gives 0 validator errors and 0 warnings. Run the repo's `gltf-validator` from the test.
5. **Circle and arc paths for `sweep`:** add analytic `circle`, `arc` and `helix` path kinds (centre, axis, radius, angles, pitch). Segment count comes from a chord-error tolerance, and the ring closes without a seam.
   **Test:** a circle sweep has the analytic length and volume within tolerance, and has no seam vertices.
6. **Coverage-aware UV packing:**
   - `uv_pack` gains `target: coverage`. It merges tiny islands where seams allow, scales islands for even texel density, and runs a packing search over margin and rotation for best coverage within a time cap.
   - It reports coverage and texel density.
   - `uv_smart_project` gains a minimum island area, to avoid hundreds of slivers on notched rings.
   - **Test:** on a notched ring (360 ticks), coverage goes from the smart-project baseline to at least a stated value worked out in the test, and stays deterministic.
7. **Texture size per material:**
   - `bake` and the material rewiring support an atlas size per material, or per channel set, so a small part doesn't get a full-size atlas.
   - `bake` reports the GPU memory estimate using the judge's documented formula.
   - **Test:** three materials baked at 2048, 1024 and 512 give images of those sizes, and the reported estimate matches the hand-worked value.

## End-to-end

`test/mcp-polish-2.test.ts` builds, through MCP tools only (no `run_python`):
- an engraved brass ring with degree numbers every 30° and two zodiac symbols, swept on a circle path;
- a veined marble plinth.
It cleans the meshes, packs UVs for coverage, bakes with per-material sizes and exports with default options. The judge (`blendworks judge`) then passes it against a strict spec in the test:
- `faces.maxDegenerate: 0`;
- `gltf.validator` with `maxErrors: 0` and `maxWarnings: 0`;
- texture rules;
- `parts.maxFloating: 0`.
The test renders close-ups for the judge to view.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:**
  - bridge: `bridge/blendworks_bridge/**` (commands, presets, procedural, baking, uv packing, shapes and new modules);
  - `bridge/tests/**`;
  - `test/` (new files, and existing tests asserting changed behaviour; list them);
  - `src/mcp/instructions.ts`;
  - section 1 and the command table of `docs/DESIGN.md`.
  Do not touch `src/judge/` or `bridge/judge/`.
- **Files shared with other open jobs:** none.
- **Environment:** `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe`. At most `BLENDWORKS_JOBS` (2) Blender processes. Iterate with `check:fast`, and run `check` once at the end at low priority: `cmd //c "start /low /wait /b cmd /c npm run check"`.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Each test above fails when its behaviour is broken. Prove each by breaking the code once.
3. The judge runs the end-to-end build, judges it, and views the close-ups: legible engraving, veins that read as marble.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
