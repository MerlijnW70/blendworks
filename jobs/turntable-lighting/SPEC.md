# Job: Turntables, lighting presets and animation contact sheets

Agents and hirers judge an asset by looking at it, and research on Blender agents shows that render-and-critique loops are what make them work (SceneCraft lost most of its score without its visual review). Blendworks renders previews and judge views, but has no turntable, no animation strip and no lighting setups beyond a world colour or HDRI, so an agent cannot show a moving asset or present it the way a store page or a review would.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`render_turntable`:** renders N evenly spaced views around a target (or the whole scene) at a chosen elevation, framing fitted to bounds, as PNG frames, an animated WebP/GIF, and an MP4 (H.264) where the Blender build supports video output; deterministic camera path; optional ground shadow catcher; device and sample settings as in `render_preview`.
2. **`render_clip_sheet`:** for an animation clip, renders a contact sheet (a grid of evenly spaced frames, front and side) and optionally a video of the clip, using the clip's NLA track as the glTF export does; reports the frames rendered.
3. **`lighting_preset`:** studio (three-point with soft boxes), product (white cyclorama), outdoor day, overcast, golden hour and night, each with documented light types, energies in physical units, colour temperatures and a matching world; replaces only the lighting it created, so repeated calls do not pile up lights.
4. **Agent view loop:** `render_preview` and the new commands return image content the MCP server can pass to the agent, capped in size; one documented way to render a small multi-view strip in one call for critique.
5. **Routing, docs and MCP:** metadata, held-out benchmark intents without lowering floors, command reference, one short line through the instructions mechanism in place on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: frame count and camera angles of a turntable; the target stays fully in frame in every view; a clip sheet's frames match the clip's evaluated poses at the stated times; repeated `lighting_preset` calls leave exactly one preset's lights; physical units recorded in the reply. No wall-clock bounds (see CONTRIBUTING).

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, `commands/render.py` and the preview rig module where reuse needs it, `src/mcp/**` (image content passing), `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs own `src/judge/**` and `bridge/judge/**`; mcp-instructions owns the instructions and routing mechanism until it lands; rebase on it.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders a turntable of the engraved rings example under three presets and a clip sheet and video of the characters example's walk, and reviews them.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
