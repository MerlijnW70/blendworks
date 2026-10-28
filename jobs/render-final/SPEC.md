# Job: Final-quality renders with camera, exposure and atmosphere

Blendworks renders previews capped at 1024 px and 64 samples, with no depth of field, no exposure or tone control beyond defaults, no motion blur and no atmosphere. Photographic images get much of their realism from these: a lens with aperture and focus, correct exposure under the view transform, aerial perspective that softens and tints distant objects, and enough samples with denoising to remove noise. Add a final-render path an agent can drive and a judge can reproduce.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`render_final`:** renders from a named camera at up to 4096 px with adaptive sampling (noise threshold and a sample cap), denoising (OpenImageDenoise, with albedo and normal passes), GPU when available and CPU otherwise, a time budget that stops cleanly, and outputs PNG/EXR plus optional passes (depth, normal, albedo, cryptomatte-style object IDs); deterministic for a seed where Blender allows, with the exceptions stated.
2. **Camera controls:** `camera_setup` for focal length, sensor size, aperture (f-stop) and focus distance or focus object (depth of field), shift, and a "physical" exposure helper (EV from aperture, shutter and ISO mapped to Blender's exposure), plus the view transform and look (AgX and its looks) with documented defaults.
3. **Atmosphere:** `atmosphere` adds aerial perspective and haze as a volume (world or a bounded domain) with density by height and distance in metres, sun-scatter tint, and optional ground fog; documented cost and a preview-friendly fallback.
4. **Motion blur** for animated clips, with shutter in frames.
5. **Docs and MCP:** command reference, a "photographic look" workflow, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: depth of field blurs objects off the focus distance and keeps the focused one sharp (a measurable edge-sharpness ratio); exposure changes mean luminance by the predicted factor per EV; haze reduces contrast with distance monotonically; the time budget stops a render and reports it; passes are written. Small render sizes and sample counts in tests, so they run in the CPU-only judge image; no wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image, where there is no GPU).
- **Allowed files:** new bridge modules and commands for final render, camera and atmosphere, `commands/render.py` and the render-session module where reuse needs it, `src/mcp/**` for long-running call handling if needed, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, on Windows and in the judge image.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the showcase meadow (trees, rocks, scanned textures, HDRI) at 2048 px with depth of field on the near rock, exposure for golden hour and light haze, and compares it with the preview render.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
