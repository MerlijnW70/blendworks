# Job: Photographic light — exposure, colour and air like a real camera on a real day

Renders read somber, grey and dark although the parts are realistic. The causes are three defaults:
- **Air:** too thick. The valley mist and the haze default far denser than a clear day: real clear mornings see 20–50 km, and morning mist is a thin layer that lifts as the sun rises.
- **Exposure:** too cautious. The automatic exposure protects highlights and leaves the subject a stop or more under, where a photographer meters the subject.
- **Colour view:** neutral and flat, without the contrast and saturation response of a camera.

Fix these in general code, the way a camera and the atmosphere work. Do not grade after the render.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Exposure like a camera.**
   - The automatic exposure meters the scene the way cameras do: evaluative or centre-weighted on scene-referred luminance, with the subject at middle grey (18 %).
   - It gives an exposure value consistent with the scene's physical luminance, checked against the sunny-16 rule and the published EV tables for daylight, overcast and twilight.
   - Highlights may clip where a camera's would.
   - The chosen EV and the metering mode appear in the result.
2. **A camera colour response.**
   - A default view, look and tone curve with the contrast and saturation of a typical digital camera's standard picture profile. Derive it from published camera or film response data, or from measured references, and state the source.
   - White balance comes from the dominant illuminant (sun, sky or overcast) by its correlated colour temperature, like a camera's auto white balance, with presets as an option.
   - Existing explicit settings keep working.
3. **Air by meteorology.**
   - The default `weather` and `atmosphere` give visibility by condition, from cited climatological ranges: clear about 20–50 km, hazy 5–10 km, mist 1–5 km, fog under 1 km.
   - Valley or radiation mist forms only under its conditions: early morning, low wind, high humidity, low ground. Its thickness (a few metres to tens of metres) and density come from cited ranges.
   - The mist thins and lifts as the sun rises and warms the air, by a stated rule.
   - The distant-land valley mist uses these rules instead of a fixed default.
4. **Sun and shadows.**
   - Under clear and fair weather the direct sun keeps its strength and colour through the air, by the atmosphere's extinction, so shadows stay crisp and the light warm at low sun.
   - Direct and sky light are in the correct ratio for the sun height, checked against published direct/diffuse ratios.
5. **Working with what exists.**
   - The example scenes (`liquid_lake`, `weather_scene`, `world_scale`, `horizon_views`) render with the new defaults.
   - Explicit user settings override every default.
   - `render_final` behaviour for explicit settings is unchanged.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- metering puts a grey card at the stated middle-grey value within a tolerance;
- EV under full sun matches sunny-16 within a stated tolerance;
- the tone response matches its reference curve within a tolerance;
- white balance neutralises a grey card under sun, overcast and low sun;
- the default clear-day visibility lies within the cited range;
- mist forms only under its conditions, and thins as the sun rises;
- shadow contrast under sun exceeds a stated ratio;
- the direct/diffuse ratio is within the cited range for three sun heights.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes:
  - no post-render grading or filters;
  - every default comes from cited physical or photographic data;
  - no per-scene tuning.
- **Allowed files:**
  - the weather, sky and atmosphere modules and commands, and the valley-mist module;
  - `camera_setup` and the camera exposure and colour parts of `render_final` and the render outputs;
  - `docs/examples/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the lake example at morning, noon and evening, and a valley view from `horizon_views`, all with `render_final` at default settings. Compared with CC0 photographs of similar places at the same times of day, each has the brightness, contrast, colour and clarity of a real photograph, not somber or grey.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
