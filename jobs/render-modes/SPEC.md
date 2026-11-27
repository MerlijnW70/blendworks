# Job: Render modes — clay, wireframe and normals in final renders

`render_final` renders only with the scene's own materials. Judging form needs more: the landscape jobs are accepted on clay renders made with `render_final`, and a mesh's topology is checked from a wireframe. Today only `render_preview` has clay, wireframe and normals views, capped at 1024 px and 64 samples. Its wireframe adds geometry per edge and refuses scenes above 400,000 edges, so it fails on any terrain region. Add those views to `render_final` and make the wireframe work on meshes of any size.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Shading option on `render_final`:** a `shading` argument with at least `shaded` (the default, unchanged behaviour), `clay`, `wireframe` and `normals`. Each view keeps the scene's camera, lights, world, sky, clouds, depth of field, motion blur, passes and output formats. Each changes only the surface materials, and only for that render: after the call the scene's materials, modifiers and objects are exactly as before, including after a failed or timed-out render.
2. **Clay:** one neutral, matte grey material on every surface, shaded by the scene's own light and sky.
   - Volumes keep their form only where they describe shape (liquids render as clay surfaces).
   - Hair and particles turn grey with the rest.
   - Instanced and scattered objects are included.
   - `render_preview` clay and `render_final` clay share one material definition.
3. **Wireframe at any size:**
   - Edges are drawn at render time without adding geometry: Cycles' Wireframe node in pixel size, or an equivalent.
   - The line width is stated in pixels and stays the same at every distance.
   - The edges are the mesh's real edges, after modifiers, as the render sees them. Lines are not drawn across each quad's diagonal unless asked.
   - It works on a mesh of at least 5 million triangles within the judge's memory.
   - `render_preview` wireframe uses the same method, so its 400,000-edge refusal goes away or rises to a stated, tested limit.
4. **Normals:** world-space normals as colours, matching `render_preview` normals.
5. **Working with what exists:**
   - Every existing caller of `render_final` and `render_preview` keeps working unchanged.
   - Routing sends "clay render", "wireframe render" and "show the topology" requests to the right tool.
6. **Docs and MCP:** command reference and the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- a clay render of a coloured scene has near-zero colour saturation on its surfaces;
- the scene's materials, modifiers and object count are unchanged after each view and after a forced failure;
- a wireframe render shows lines on a known grid at the expected pixel positions, and their width stays within a stated tolerance at two distances;
- a 5-million-triangle mesh renders as a wireframe within the memory budget;
- normals colours match `render_preview` within a stated tolerance;
- `shaded` output is unchanged from before this job.

Small renders, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief. The check must pass in the Linux judge image, where there is no GPU.
- No quick fixes: fix in the general render path, with no scene-specific or test-specific cases.
- **Allowed files:**
  - `bridge/blendworks_bridge/commands/render_final.py`, `commands/render.py`, `preview.py`, `render_outputs.py`, `limits.py`;
  - new bridge modules for render views;
  - `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders, with `render_final` at default settings, a terrain from `heightfield` of at least 2 million triangles and a tree from `grow_tree` with leaves, each in `clay`, `wireframe` and `normals`. Each view reads clearly, and the wireframe shows the real topology at uniform line width.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
