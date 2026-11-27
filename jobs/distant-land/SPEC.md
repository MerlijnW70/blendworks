# Job: Distant land — land, forest and air to the horizon around any scene

Every Blendworks landscape ends in a flat green plane or a hard edge a few kilometres out. The far land has none of the near land's character: no ridges behind ridges, no forest texture, no fading into the sky. The air is wrong as well:
- `weather` caps its haze at 10 km (`HAZE_REACH`);
- `add_camera` clips at 10 km;
- `atmosphere` ground fog is measured from z = 0 and grows without bound below it, so a terrain lying below zero turns the whole frame white.

A photograph of a lake or a valley shows land to the horizon, layers of hills fading blue, forest as texture on far slopes, and mist lying in low ground. Add this as a general layer that works around any scene Blendworks builds now, and later around `landforms` regions. This job takes the distant-land, forest and air parts of the `horizon` job forward. The `horizon` job keeps the composition helper and the finished scene presets.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering; `world-scale` lands before or during this job.

## Required

1. **Distant land.**
   - A `distant_land` command surrounds a given region with land out to a stated distance of at least 80 km in every direction. The region is terrain objects, or a bounding box with a ground object.
   - The region's border heights are matched within a stated tolerance, with no visible seam, step or change of character there.
   - The land continues the region's character by its measured statistics: relief, slope distribution, dominant wavelengths, and the share and size of water and flat ground. Two styles are offered: rolling land, and ranges behind ranges.
   - Level of detail falls with distance in nested rings, with no cracks.
   - The curvature of the earth is applied, using a stated radius.
   - The ground material continues the region's ground at a matching level of detail.
   - A stated triangle and memory budget holds within the 8 GB judge.
2. **Distant forest.**
   - Forest on far land is built from Blendworks' own tree species. Use impostors (cards or an octahedral atlas baked with colour, normal and depth) or an equivalent forest canopy surface.
   - Forest is placed by rules: slope, height, water and a stated cover share.
   - It blends into instanced trees near the camera with no visible switch: a luminance step under a stated value.
   - Silhouettes match their source within a stated IoU.
3. **Air at landscape scale.**
   - Aerial perspective makes far land fade and turn towards the sky colour by the atmosphere's extinction, out to the horizon.
   - `weather` haze works at any visibility; there is no 10 km cap.
   - Cameras get a far clip that covers the scene; `add_camera` and `camera_setup` no longer cut land at 10 km.
   - `atmosphere` ground fog is defined relative to the ground: a base height or the terrain's low ground. It is bounded below, so fog lies in valleys and over water as a layer of stated thickness and density, wherever the terrain sits in z.
   - Valley mist follows low ground.
4. **Working with what exists.**
   - The existing example scenes (`liquid_lake`, `weather_scene`, the world-scale example) gain an option that adds distant land, forest and air.
   - With that option off they render as before.
   - `render_final` renders them within the judge's memory.
   - World-space precision far from the origin follows `world-scale`.
5. **Docs and MCP:** the command reference and a "to the horizon" workflow. Routing for "land to the horizon", "distant mountains", "forest in the distance" and "mist in the valley".

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- border heights match within the tolerance;
- the distant land's measured statistics match the region's within stated tolerances;
- land at a stated distance drops by the earth's curvature within a tolerance;
- the colour of far land moves towards the sky colour with distance, by the extinction, within a tolerance;
- impostor IoU;
- no luminance step at the forest switch;
- haze above 10 km visibility works in `weather`;
- nothing is clipped at 10 km;
- ground fog below z = 0 forms a bounded layer and does not fill the frame;
- the budgets hold;
- the same seed repeats.

Small grids and renders, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- Blendworks builds everything itself: no downloaded heightmaps, textures, HDRIs or models.
- No quick fixes:
  - no backdrop images;
  - no painted horizons;
  - no fog used to hide missing land;
  - fixes go in the general code.
- **Allowed files:**
  - new bridge modules and commands for distant land, impostors and valley mist;
  - `weather_build.py` and the haze parts of `weather`;
  - `commands/atmosphere.py` and the haze modules;
  - the camera clip parts of `commands/lights.py` and `camera_setup`;
  - `render_final` only where distant land needs it;
  - the example scripts' options;
  - `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default. The machine is shared.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders, with `render_final` at default settings:
   - the morning lake scene with distant land, forest and valley mist;
   - a valley scene looking along a valley to ranges behind ranges;
   - a view from a hill over rolling land to a flat horizon.

   Compared with CC0 reference photos of the same kinds of view, each shows land and forest to the horizon fading into the sky, with no edge, plane or seam.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
