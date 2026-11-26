# Job: Procedural sky and weather, from clear sun to thunderstorm

Blendworks lights outdoor scenes only with a uniform world colour or an HDRI image. A scene that should be built entirely by Blendworks has no sky of its own, and `set_world` is broken after `set_world_hdri`: it sets the Background node's default colour while the environment texture stays linked, so the old HDRI keeps showing; `new_scene` does not reset the world either. Add a physically based, procedural sky with clouds and weather that covers the whole range an outdoor scene needs, from a clear sunny day through every common cloud type to a dark thunderstorm, with the sun light and exposure that belong to each.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Sky:** a `sky` command builds a procedural sky in the world from Blender's sky models (Nishita or multiple scattering, whichever is current), with the sun placed by elevation and azimuth in degrees or by date, local time, latitude and longitude, plus air, dust and ozone. A sun lamp is created or updated so its direction, colour and strength match the sky's sun, including twilight and the sun below the horizon.
2. **Clouds:** clouds that look like real clouds from the ground and at the horizon, sized in metres and placed at their real altitudes, in the common genera at least: cumulus (fair weather to towering), stratocumulus, stratus and overcast, altocumulus, cirrus, and cumulonimbus with an anvil. Coverage (0 to 1), base height, thickness, density, wind drift direction and seed are parameters. Clouds cast shadows on the ground and dim the sun as real clouds do. A volumetric form for final renders and a cheaper form for previews and EEVEE, with the cost of each stated.
3. **Weather presets and one continuum:** named presets (clear, hazy, fair-weather cumulus, scattered, broken, overcast, light rain, heavy rain, thunderstorm, plus golden hour and dusk variants where they make sense) and a single `storm` value from 0 to 1 that moves continuously from clear to thunderstorm, darkening and cooling the light, lowering and thickening the cloud base, raising coverage and softening shadows. Every preset is the continuum or an explicit override of it, documented.
4. **Storm details:** rain as visible streaks or veils in the distance and optional rain on the camera's foreground, wet-ground darkening as an option for materials that support it, and optional lightning (bolt geometry and a flash light), all seeded and off by default except where a preset turns them on.
5. **World fixes:** `set_world` replaces whatever drives the background (image, sky, clouds) with the uniform colour it is asked for; `new_scene` leaves a clean default world; switching between `set_world`, `set_world_hdri` and `sky` in any order shows only the last one. Each command reports what it replaced.
6. **Docs and MCP:** command reference, a "weather and sky" workflow with the presets and their look, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: the sun lamp's direction matches the sky's brightest point within a stated angle for several sun positions; the sun's colour reddens and its strength falls towards the horizon; the cloud coverage measured from a render of the sky hemisphere matches the coverage parameter within a stated tolerance; scene luminance and shadow contrast fall monotonically with `storm`; clouds shadow the ground (a sunlit patch and a shaded patch under a cloud differ by a stated factor); the same seed gives the same sky and another seed changes it; `set_world` after `set_world_hdri` or `sky` shows a uniform background; `new_scene` resets the world. Small render sizes and sample counts, CPU, no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- Blendworks builds the sky itself: no HDRI or image downloads in the presets or the tests.
- **Allowed files:** `bridge/blendworks_bridge/commands/lights.py`, the scene-reset code in the `new_scene` command, new bridge modules and commands for sky, clouds and weather, `render_final` and `atmosphere` only where they need to read the sky or clouds, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders one outdoor scene built only with Blendworks (terrain, a dry-stone wall, a tree, ground cover) under clear, fair-weather cumulus, overcast, heavy rain and thunderstorm at golden hour and at noon with `render_final`, and compares each with CC0 reference photos of the same weather: each reads as a photograph of that weather.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
