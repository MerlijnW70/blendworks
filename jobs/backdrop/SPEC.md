# Job: Backdrops and scene composition for convincing environments

Scenes built with Blendworks end in an empty plane under an HDRI: there is no transition from the dressed foreground to the distance, no hills, tree lines or water, and no framing. Environment artists build depth in layers (foreground detail, midground set dressing, distant terrain and impostors, sky) and compose shots with a few rules of thumb. Give agents the tools to build that depth cheaply and to compose a shot.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`backdrop`:** generates distant terrain rings or panels (from `heightfield` and `erode`, at decreasing resolution with distance), tree lines and forest edges as impostor cards baked from Blendworks trees, and optional water planes with shoreline blending; aligned to the HDRI horizon and sun direction; within a stated triangle and texture budget.
2. **`impostor_bake`:** bakes any object (a tree, a rock cluster) into impostor cards or an octahedral impostor atlas (colour, normal, depth) for distant use, with a test that its silhouette matches the source within a stated IoU from the views it was baked for.
3. **Composition helpers:** `frame_shot` places a camera to frame given subjects by rule-of-thirds or centred composition at a focal length, with a horizon line position and foreground/midground/background layering report (which objects fall in each depth band and their screen coverage).
4. **Horizon match:** a check that the HDRI horizon and the scene horizon align (reporting the angle mismatch) and a command to rotate or offset the HDRI to the sun direction the scene uses.
5. **Docs and MCP:** command reference, an "environment shot" workflow, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include impostor silhouette IoU, budget limits, thirds placement within a stated tolerance in normalised screen coordinates, and horizon mismatch measurement. Container-friendly sizes; no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image).
- **Allowed files:** new bridge modules and commands, the terrain, tree and lighting modules where reuse needs it, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, on Windows and in the judge image.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds the showcase meadow with a backdrop of hills, a forest edge of impostor trees and a framed hero shot, and reviews it against the same scene without them.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
