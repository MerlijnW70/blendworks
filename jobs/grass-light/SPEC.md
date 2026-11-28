# Job: Grass light — sunlit grass is bright, as in a photograph

With camera-like exposure on `main`, dense grass under a high sun renders near-black. The measurements are in the job workspace:
- the sun adds 0.009 luminance on grass, against 0.24 on bare ground;
- clay shading is 5× darker on grass than on open ground;
- the grass reads about 0.02 under both morning and noon sun.

Real sunlit grass is among the brighter parts of a summer landscape, because the top blades are sunlit and light passes through the leaves. The far meadow reads pale mint (material albedo about 0.25), and water reads milky at grazing angles.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Diagnose.**
   - Find why direct sun barely reaches the visible blades. Candidates: blade orientation and normals (back faces, normals pointing down or sideways); blade density and height, giving self-shadowing beyond a real canopy's; no transmission; a too-dark blade albedo; shadow-terminator or light-path settings.
   - State the measured cause, with renders of a grass patch under a noon sun before and after.
2. **Physically based grass.**
   - Blade geometry and orientation follow measured leaf-angle distributions (for example an erectophile distribution for grasses, with a cited leaf area index).
   - The blade material has cited reflectance and transmittance for green grass leaves (PROSPECT-style values or measured spectra), with translucency, a two-sided shader and correct normals.
   - Canopy-level reflectance, measured on a flat patch under a high sun, matches cited canopy albedo for grassland (about 0.18–0.26 broadband, with a green peak).
3. **Far meadow and lawn materials.**
   - The bare far ground and LOD grass materials take their albedo and colour from the same canopy model, so near and far grass match in brightness and hue across the distance.
   - No pale mint.
4. **Water at grazing angles.**
   - Check the water shader's Fresnel, roughness and colour against physical values.
   - Milky water must come only from what the water truly reflects (a bright sky), not from a wrong IOR, roughness or scattering.
   - Fix it if wrong. If it is right, state the measurement that shows it.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- under a noon sun, a grass patch's mean luminance is at least a stated fraction of bare ground's;
- canopy reflectance is within the cited range;
- leaf transmittance is above zero and within its cited range;
- near and far grass differ in luminance and hue by less than stated bounds at a stated distance;
- the water's reflectance at 85° incidence matches Fresnel for its IOR within a tolerance.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes: no exposure or grading tricks, and cited optical data only.
- **Allowed files:**
  - the ground-cover blade, material and preset modules;
  - the grass and ground material presets;
  - the water shader module;
  - `docs/examples/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the lake example at noon and morning, and a grass close-up under a noon sun, with `render_final` at default settings. Compared with CC0 photographs of sunlit meadows, the grass reads bright and green, not near-black, and near and far grass match.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
