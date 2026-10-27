# Job: Noise in metres and terrain tiles

Blendworks can only displace with the legacy Blender textures (size, depth, intensity and contrast, with no Hurst exponent, lacunarity, ridges or warp) and with `displace_noise` jitter or dents. Natural surfaces need a noise stack whose roughness and scale are set in metres. Build `noise_displace` (plan item P1 in `docs/research/natural-shapes.md`) and `heightfield` on top of it (P2), from the papers cited there.

## Base

- **Base commit:** eab1e70. Rebase onto the latest `main` before delivering.

## Required

1. **`noise_displace` command:**
   - Parameters: `name`, `amplitude` (metres, a hard bound as in `displace_noise`), `seed`; `basis` (`perlin`, `worley_f1`, `worley_f2_minus_f1`); `octaves` (1–12), `lacunarity` (default 2), `hurst` (0–1, default 0.7), `mode` (`fbm`, `ridged`, `billow`), `ridge_offset`; `warp` (metres) and `warp_octaves`; `scale` (wavelength of the first octave in metres); `direction` (`normal`, `z`); the face selector and `vertex_group` mask, as in `displace_noise`.
   - Noise is evaluated at world coordinates in metres, so the same object scaled or moved shows detail at the same real size, and two touching objects continue one field.
   - fBm uses the per-octave gain `G = 2^−H`; ridged is `ridge_offset − |n|`; billow is `|n|`; warp is `p + warp·q` with `q` a second fBm. Sources as cited in section 1.4 and P1 of the research document.
   - Implemented in numpy on the bridge side, deterministic by seed and independent of vertex order. Coincident vertices move together, so a mesh with split normals or UV seams does not tear.
   - The reply reports the displaced vertex count, the largest displacement and the measured height range.
2. **`heightfield` command:**
   - Parameters: `name`, `size` [x, y] in metres, `resolution` (vertices per side, capped by the bridge's vertex limit), `tile` [i, j]; the noise fields of `noise_displace`; `height` in metres, `base_height`, `skirt` (a closed underside so the tile is a closed solid); `attributes` (any of `slope`, `height`, `curvature`, written as named float attributes for later masks).
   - Noise is sampled at world coordinates `tile × size + local`, so neighbouring tiles share their edge heights exactly.
   - UVs cover the tile without stretch beyond what the height gradient implies, and continue across tiles.
3. **Routing, docs and MCP:** both commands carry `family`, `intents` and `nearest` metadata like the other commands, the tool-selection benchmark gains held-out intents for them without lowering its floors, and the command reference and `src/mcp/instructions.ts` stay accurate.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- On a 200 m × 200 m plane with 1 m spacing, the second-order structure function `E[(h(x + l) − h(x))²]` grows as `l^(2H)`: the fitted log–log slope over lags of 2 to 32 m is within ±0.15 of `2H` for `H = 0.5` and `H = 0.8` (fBm, perlin basis, enough octaves to cover the lag range). Work out the octave count in the test.
- No vertex moves more than `amplitude`; the same seed gives identical vertices; a different seed gives different vertices; shuffling vertex order changes nothing.
- Coincident vertices move together on a mesh with split UV seams.
- With one octave, `ridged` equals `ridge_offset − |n(p)|` at every vertex, where `n(p)` is the basis evaluated directly at the same point; likewise `billow` equals `|n(p)|`.
- Moving the object by a whole number of first-octave wavelengths does not make the field repeat (no lattice-aligned artefacts: the noise at integer lattice points is not constant).
- Worley `F1` is zero at feature points and `F2 − F1` is zero on cell borders, checked against a brute-force nearest-point search.
- Heightfield tiles [0, 0] and [1, 0] share the heights of their common edge to 1e-9; a zero-amplitude noise on a tilted plane gives a constant `slope` attribute equal to the tilt; with `skirt` the tile passes the judge's `manifold` rule.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`.
- Write every method from the papers cited in `docs/research/natural-shapes.md`. Do not copy from GPL add-ons (A.N.T. Landscape and others listed in section 6) or from code snippets in articles.
- **Allowed files:**
  - new modules under `bridge/blendworks_bridge/` and `bridge/blendworks_bridge/commands/`; `commands/__init__.py` and `kit_limits.py` minimally;
  - `src/mcp/**`, `bench/tool-selection/**`, `test/**` and `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** judge-onepass owns `src/judge/**`, `bridge/judge/**`, `commands/uv_pack.py`, `uvlayout.py` and `texel.py`; do not touch them. The job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script, included in `docs/examples/`, that builds a 2 × 2 heightfield tile set with ridged, warped terrain and a rock made with `noise_displace` on a subdivided primitive, and reviews its renders: no seams between tiles, no visible lattice or banding, and detail at large, medium and small scale.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
