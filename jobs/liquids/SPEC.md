# Job: Liquids — materials, bodies of liquid and liquid in containers

Blendworks can build terrain, rocks, plants, trees, ground cover, sky and weather, but no liquid at all: no water surface, no liquid material, no filled glass. Liquids are more than water: they differ in how they pass light (clear with coloured absorption, milky with scattering, emissive like lava) and in how thick they are (water to honey to mud). Add liquids that Blendworks builds itself and that fit into the scenes it already builds.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Liquid materials:** a `material_liquid` command with physically based presets at least for water (fresh, sea, muddy), wine, beer with foam, oil, milk, juice, coffee, paint, honey, syrup, mud, lava and molten metal. Each preset states its index of refraction, absorption colour and distance in metres, scattering (for milk, paint, mud), emission and temperature where it glows (lava, metal, with a cooling crust), roughness and foam or bubbles where relevant. Values come from cited sources.
2. **Bodies of liquid:** a `liquid_body` command for open liquid at world scale: ocean and sea (wave spectrum by wind speed and fetch, foam on crests, a beach or shore line), lakes and ponds (calm surface with ripples), rivers and streams that follow a path or the lowest line of a terrain (flow direction, speed and width, surface detail aligned to the flow), and puddles that fill hollows of a surface up to a level. Depth is real: the bottom shows through shallow water and fades with depth by the material's absorption.
3. **Liquid in containers:** a `liquid_fill` command fills any closed or open container mesh (glass, bottle, cup, bowl, pan, bucket, tank) to a level or a volume in litres, with the surface fitted to the inner wall, a meniscus at the rim, an optional tilt, and the liquid separated from the glass by a thin gap so refraction renders correctly. Drips, a pour stream and spills (a puddle shape with a defined area) are part of it.
4. **Working with what exists:** the liquid surface takes the scene's wind from `weather` (ripples and waves follow it), reflects the sky and clouds, receives cloud shadows; `scatter` and `ground_cover` can mask out liquid areas and add wet shores; shores, rocks and ground near the water line get the wet-ground darkening from `weather`; `atmosphere` haze applies over water; `render_final` renders it without fireflies at its default settings.
5. **Docs and MCP:** command reference, a "liquids" workflow with each preset's look, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: refraction through a filled glass shifts a background edge by the amount the preset's index predicts; light through clear liquid falls with depth by the preset's absorption (Beer–Lambert) within a stated tolerance; milk and paint are opaque at a stated thickness while water is not; lava emits and its crust does not; the ocean's wave height follows the wind speed by the stated spectrum; a river follows the terrain's lowest line and flows downhill; a puddle stays inside its hollow and its area matches; `liquid_fill` puts the stated volume in litres into a container of known volume within a stated tolerance and the surface never crosses the wall; ground cover is absent under water and shores are wet; ripples follow the weather's wind direction; the same seed repeats. Small render sizes and sample counts, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds every liquid itself: no downloaded textures, HDRIs or models in presets or tests.
- Fluid simulation (pouring, splashing, viscous coiling) is out of scope; a later job covers it.
- **Allowed files:** new bridge modules and commands for liquids, the scatter and ground-cover mask code and the `weather` wetness code where liquids need to plug in, `render_final` only for render settings liquids need, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds two scenes with Blendworks only and renders them with `render_final`: an outdoor scene (terrain with a river into a lake, rocks at the shore, ground cover, trees, sky with fair-weather cumulus) and a still life (glasses of water, wine, milk and oil, a jar of honey, a puddle of spilled coffee on a wooden table), and compares each with CC0 reference photos: each reads as a photograph.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
