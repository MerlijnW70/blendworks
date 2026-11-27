# Job: Horizon — land to the horizon, air in the valleys, and the finished landscapes

A landscape that stops at the edge of its region, or ends in a flat plane under an HDRI, does not read as a photograph. Real views go on to the horizon: ranges behind ranges fading into the sky, forests reduced to texture, mist lying in the valleys, clouds caught on the peaks, the land dropping away with the curvature of the earth. Add distant land and air, and put all four landscape jobs together in finished scenes. Last of four landscape jobs (`landforms`, `cliffs`, `surface`, `horizon`).

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; `landforms`, `cliffs` and `surface` land before this job.

## Required

1. **Distant land:** land beyond the region to the horizon in every direction the camera sees, continuous with the region (no seam, step or change of character at the border), at detail that falls with distance, with ranges behind ranges; the curvature of the earth for land more than a few kilometres away; and the ground rules, snow and biomes of `surface` carried on at a matching level of detail.
2. **Distant vegetation:** forests and tree lines far away as impostor cards or an octahedral atlas baked from Blendworks trees (colour, normal, depth), whose silhouette matches the source within a stated IoU, blending without a visible switch into instanced trees near the camera; within a stated triangle, texture and memory budget.
3. **Air:** aerial perspective from `atmosphere` and the `sky` so far ridges fade and turn blue towards the sky colour by the atmosphere's extinction; valley fog and mist lying in low ground by a stated height and density; low clouds and cloud caps on peaks from the `clouds` tool; haze that follows the `weather` state.
4. **Composition:** a `landscape_shot` helper that, given a region and a subject (a peak, a lake, a cliff), proposes camera positions, heights and focal lengths a landscape photographer would use (foreground interest, rule of thirds, a horizon placement, layers of depth), checks that the subject is visible and not hidden by terrain, and sets the sun for good light (golden hour, side light) through the `sky`.
5. **Finished landscapes:** a `scene` preset for each acceptance landscape below that builds it end to end from the four landscape jobs, liquids, sky, clouds, weather, trees, ground cover and rocks with one shared state (wind, season, weather, time) and one call, and reports what it built and its cost.
6. **Working with what exists:** `render_final` renders every preset at its default settings within the judge's memory; the shared wind direction is one value across clouds, water, dunes, snow and vegetation; nothing floats, nothing grows in water or on cliffs.
7. **Docs and MCP:** command reference, a "landscapes" workflow from region to finished render, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: distant land and the region share their border heights within a stated tolerance; land at a stated distance drops by the earth's curvature within a stated tolerance; distant land's colour moves towards the sky colour with distance by the atmosphere's extinction within a stated tolerance; impostor silhouettes match their source within the stated IoU; the switch from impostors to instances shows no luminance step above a stated value; valley fog is denser below its height than above; `landscape_shot` keeps the subject visible and inside the frame; a scene preset leaves no floating object and no plant in water or on a cliff; triangle, texture and memory budgets hold; the same seed repeats. Small renders, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds everything itself: no downloaded heightmaps, textures, HDRIs or models. This job replaces the never-built `backdrop` job.
- **Allowed files:** new bridge modules and commands for distant land, impostors, valley fog, shots and scene presets, the `landscape` region code where distant land joins it, `atmosphere` and `render_final` only where distant land and fog need them, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds with Blendworks only, each in one call, five landscapes rendered with `render_final` at a fitting time of day: an alpine valley with a river into a lake below snowy peaks and forest on the slopes; a desert canyon with layered walls and scree; a sea coast with cliffs, an arch, a beach and waves; a volcano with dark basalt and sparse vegetation; and rolling farmland hills fading to distant ranges with morning mist in the valleys. Compared with CC0 reference photos of the same kind of place, each reads as a photograph, with land to the horizon.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
