# Job: Custom shader graphs, scene hierarchy, and a better worn-metal look

Three open gaps for agents remain from the audit and the last asset rounds:
- Agents can only use the procedural presets, so a custom shader still needs raw bpy.
- Agents cannot create empties or collections to structure a scene.
- The worn-metal and brass wear layer shows crack-like lines on smooth brass (see the polish-2 test ring).

Close them properly.

## Base

- **Base commit:** `8f55cfd`. Rebase onto the latest `main` before delivering.

## Required

1. **`material_nodes`:** build a material from a declarative node graph.
   - The graph is a list of nodes (type, name, inputs, settings) and a list of links (from node and socket to node and socket).
   - Node types come from a curated, documented allow-list of shader, texture, colour, vector and converter nodes, including Principled BSDF, noise, voronoi, wave, musgrave or noise-based equivalents, colour ramp, mix, math, vector math, mapping, texture coordinate, bump, normal map, geometry and AO.
   - There is no script node and no arbitrary property path. Unknown node types, sockets or settings are refused.
   - It validates node and link counts against caps, checks socket types for compatibility, and refuses cycles.
   - The result works with `material_layer`, `bake` (with rewire) and the glTF export path.
   - `material_info` returns a material's graph in the same format, so that it can be read back and edited.
2. **Hierarchy:**
   - `add_empty` takes a name, a display type, a size and a transform.
   - `collection_create`, `collection_link` and `collection_unlink` organise objects into collections.
   - `scene_info` reports parents and collections, and `export` keeps the hierarchy, building on the session job's ancestor export.
   - Test: an exported glb has the expected node tree.
3. **Worn metal fixed at the root:**
   - Find why the `worn_metal` preset or `material_layer` with edge or cavity masks produces a crack network on smooth, low-curvature brass. The likely cause is a voronoi or cell term, or a pointiness mask, on surfaces without curvature.
   - Fix it so that wear follows real edges and cavities, and polished brass reads as smooth, with fine directional scratches and patina in recesses.
   - Add a `brass` (aged brass) preset with typed parameters: patina amount, polish, scratch direction and scale.
   - Test: a baked smooth cylinder band shows no crack-like structure, using the deterministic statistic approach of the marble test inverted. Edge wear concentrates on a bevelled edge.

## Tests

- **`material_nodes`:**
  - a graph that reproduces a simple wood shader bakes to expected colour statistics;
  - an invalid graph (unknown node, bad socket, cycle, over the cap) is refused and leaves the scene unchanged;
  - a round trip through `material_info` gives the same graph.
- **Hierarchy:** the glb node tree is as expected after export, and collection membership is reported by `scene_info`.
- **Brass:** the statistics described in item 3, plus a render the judge views.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:**
  - `bridge/blendworks_bridge/**`;
  - `bridge/tests/**`;
  - `test/` (new files, plus existing tests that assert changed behaviour; list them);
  - `src/mcp/instructions.ts`;
  - `docs/DESIGN.md` §1 and the command table.
- **Files shared with other open jobs:** none.
- **Environment:** set `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe`, and run at most `BLENDWORKS_JOBS` Blender processes.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when a script node gets through, when the hierarchy is lost on export, or when brass shows crack-like structure again.
3. The judge views a brass band render and a custom node-graph material render.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
