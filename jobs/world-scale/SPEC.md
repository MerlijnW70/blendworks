# Job: World scale — landscapes tens of kilometres wide, and plans checked before they run

Blendworks caps every coordinate, length and tile at 10 km (`MAX_COORDINATE`). Some other limits were set for small props and stop a landscape before it is built:
- `noise_displace` amplitude stops at 100 m;
- atmosphere visibility stops at 10 km, where clear mountain air sees 50 to 300 km;
- one `heightfield` tile stops at 10 km;
- a camera cannot stand more than 10 km from the origin.

A real mountain view needs land and air from 0.5 m to over 100 km. A script that builds a scene also learns about these limits one at a time, after minutes of building. Building a mountain scene today hit five refusals in a row: amplitude, timeout argument, tile size, location, budget. Make worlds of landscape scale work everywhere, and let a caller check a whole plan before running it.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.
- `render-modes` may land first: it touches `limits.py`.

## Required

1. **Landscape scale:**
   - Coordinates, lengths and sizes may reach at least 200 km from the origin wherever a landscape needs them: object locations, cameras and their clip distances, terrain tiles, haze and fog domains, cloud fields, scatter and ground-cover regions, liquid bodies and render bounds.
   - The precision stays fine where the camera is. Choose and state the method: float32 error at 200 km is about 1.5 cm, so either show that it is enough for every tool, or add a floating origin or camera-relative placement.
   - Limits that exist for safety (memory, time, counts) stay. Each one is stated with the reason for its value.
2. **Limits from a principle:**
   - Every numeric limit in tool schemas is listed in one table (docs), each with its reason: physical range, memory, time or Blender's own limit.
   - Limits that only reflect prop scale are raised to what a landscape needs, for example:
     - displacement amplitude relative to the object's size or up to kilometres;
     - visibility to at least 300 km;
     - ground-cover budget derived from memory rather than a fixed count.
   - The same quantity has the same limit in every tool.
3. **Plans checked first:**
   - A `validate` call, or a `dry_run` flag accepted by every tool, checks the arguments of one call or of a list of calls against the schemas and against the scene state those calls would create (names that earlier calls make, targets that must exist).
   - It reports every problem at once, without running anything.
   - Scripts and the MCP path use the same check.
4. **Errors that help:** every refusal names the argument, the value, the limit, and the tool or argument to use instead where one exists.
5. **Working with what exists:**
   - The example scenes and every existing test keep working unchanged.
   - A new example script builds a landscape whose camera stands 15 km from the origin, with land and haze reaching 100 km. It renders it with `render_final`.
6. **Docs and MCP:** the limits table, the validate workflow, and command reference updates. Routing for "check my plan", "validate these calls" and "how big can a scene be".

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- each tool accepts a landscape-scale value it refused before;
- placement error at 150 km stays under a stated value;
- every schema limit appears in the limits table with a reason;
- equal quantities have equal limits;
- validate reports all errors of a bad five-call plan in one answer and runs nothing;
- validate accepts a good plan whose later calls use names made by earlier ones;
- the 15 km example renders without a refusal.

Small grids and renders, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief. The check must pass in the Linux judge image, where there is no GPU.
- No quick fixes: fix limits and precision in the general code, with no tool-specific or test-specific exceptions.
- **Allowed files:**
  - `bridge/blendworks_bridge/limits.py`, `schema.py` and the schema parts of every command;
  - the handler and request path for validation;
  - `src/mcp/**` where validation and limits are exposed;
  - `docs/**`, `test/**`, `bridge/tests/**`, `bench/tool-selection/**`, `docs/examples/**`.
  - Not the landform modules, `heightfield` or `erode` internals, which the `landforms` job owns; their schema limits may change.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the 15 km example and a deliberately broken plan through `validate`. The example renders land and haze to the horizon with no refusal. The broken plan gets every error in one answer, each naming argument, value, limit and alternative.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
