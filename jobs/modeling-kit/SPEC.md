# Job: A modelling kit for detailed hard-surface assets

The agents that built the drill rig and the pickaxe wrote raw bpy for everything. That covered sweeping profiles along paths, lathing, lofting, extruding gear outlines, placing hundreds of bolts, and multi-cutter booleans, because the bridge has no commands for these. Add them as proper, validated, transactional bridge commands, so that a detailed asset can be built with tools alone. Study the builders' own generators as the reference for what is needed: `build.py` in `scratchpad/blendworks/asset-drill-rig/` and `asset-pickaxe/` on the judge's machine. Do not copy them blindly. Design clean, general commands.

## Required

1. **Shapes from profiles** (new module, for example `commands/shapes.py`):
   - **`lathe`:** revolve a 2D profile (points in the XZ plane) around an axis, with segments, an angle, caps and a seam merge. The result is closed and manifold when the profile closes on the axis.
   - **`sweep`:** a profile (points or a named preset: circle, rectangle, rounded rectangle) along a path (points, or an existing curve object).
     - It uses parallel-transport frames, so there are no flips.
     - It supports scale along the path, twist, closed paths and end caps.
     - It supports smooth bends through optional corner fillets with a radius.
   - **`loft`:** skin between a list of cross-sections, each with its own shape, position and orientation. Sections of matching size are required, or are resampled by a documented rule.
   - **`extrude_outline`:** a 2D outline with optional holes becomes a solid with a given depth, optional bevel or chamfer and caps. This covers gear plates, brackets and signs.
   - **`gear`:** an involute or simplified tooth profile from module or pitch, tooth count, bore and thickness. It is built on `extrude_outline`. Also add `sprocket` and a roller-chain helper along a path.
   - All of these produce real meshes with UVs (documented: unwrapped along the length for `sweep` and `lathe`) and smooth or flat shading by angle.
2. **Repetition and placement:**
   - `instances` places linked copies of an object at a list of points, or along a curve or edge loop at a spacing, or on a circle. It takes rotation, align-to-normal and per-instance scale.
   - It has an option to realise the copies into one mesh, for export.
   - Shared meshes are allowed and documented.
   - `rivet_line` is a convenience on top of `instances`.
3. **Booleans at scale:**
   - `boolean` accepts `cutters: [names]`, applied in one operation through a union first, with the exact solver.
   - It cleans up afterwards (merge by distance, recalculated normals), and it refuses cleanly when the result is not manifold and the caller asked for manifold.
4. **Generic modifiers:** `add_modifier` and `apply_modifier` cover a whitelist: displace (with built-in noise textures), weld, screw, curve, simple deform, wireframe, lattice, shrinkwrap, triangulate, weighted normal, bevel (with limit method and segments) and solidify. Each has a typed schema; unknown fields are refused.
5. **Precise mesh input:**
   - `mesh_from_data` gains per-face `material_index`, per-loop or per-vertex UVs, smooth flags and creases.
   - It also gains a `path` alternative that reads a JSON file from the workspace, for large meshes.
   - The vertex cap applies to both.
6. **Selection that reaches geometry:**
   - Select faces by bounding box, by material, by normal cone, by island or by area range.
   - Add a `mesh_query` that returns face centres, normals, areas and materials, paged.
   - Add `transform_selection`, which moves, rotates or scales the selected faces or vertices.
   - Add `bevel` on selected edges with harden normals.
7. **Wear in geometry:** `displace_noise` adds a seeded, bounded vertex jitter or dents (hammer facets), with a mask by selection or vertex group.
8. **Docs:** add each command family to the table in `docs/DESIGN.md` section 1, and add short guidance to the MCP instructions (what to use for pipes, gears, bolts and turned parts).

## Tests (expected values worked out by hand where possible)

- **`lathe`:** lathing a closed profile gives the expected vertex and face counts, a manifold result, and the volume of a solid of revolution within 1 %.
- **`sweep`:** a circle swept along a 90° bend has no twist (checked through the frame continuity of adjacent rings) and the right length. Closed paths have no seam gap.
- **`extrude_outline` with holes:** the expected Euler characteristic and a manifold result.
- **`gear`:** the tooth count, outer diameter and module match.
- **`instances`:** a count along a curve at a spacing. A realised result has the summed triangle count.
- **Multi-cutter booleans:** volume after cutting N cylinders out of a box matches the analytic value within tolerance.
- **Modifiers:** every whitelisted modifier is tested for refusal of unknown fields and for a rollback on failure.
- **End-to-end:** an MCP-level test builds a small detailed prop with tools only and no `run_python` (for example a flanged pipe with a valve wheel and a bolt ring). It exports the prop, and the judge (`blendworks judge`) passes it against a small spec in the test. The test renders a close-up for the judge to view.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only these files:
  - new bridge modules and new command files;
  - `bridge/blendworks_bridge/commands/` files `geometry.py`, `modifiers.py`, `mesh_edit.py`, `objects.py`, `uv.py` and `__init__.py`;
  - `bridge/blendworks_bridge/selection.py` and `schema.py` (only additions);
  - `bridge/tests/`, `test/` (new files, plus existing tests that assert behaviour this spec changes; list them);
  - `src/mcp/instructions.ts`;
  - the command table and section 1 of `docs/DESIGN.md`.
- The session-robustness job edits `transaction.py`, `handler.py`, `registry.py`, `commands/run_python.py`, `files.py`, `scene.py` and `render.py` in parallel. Do not edit those; rebase onto the latest `main` before delivering.
- Keep the PC usable: one Blender process at a time, and run the full check at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when `sweep` frames flip, when lathe stops closing on the axis, or when multi-cutter booleans leave a non-manifold result while manifold was requested.
3. The judge builds a small detailed prop through the MCP server with tools only, judges it, and views the close-up.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
