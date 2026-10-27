# Job: Natural material presets and masks

The material presets cover wood, metals, stone, marble, concrete, fabric and dirt, but nothing for bark, moss, leaves, soil, sand or grass ground, and `material_layer` can only mask by noise, edges, cavity or vertex colour. Natural assets need masks that follow slope, height and exposure. The `stone` preset also shows hard-edged polygonal patches on curved rocks (see the `rock` render of `docs/examples/noise_terrain.py`), which read as camouflage rather than stone. Build plan item P10 of `docs/research/natural-shapes.md` and fix that fault at its root.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Presets, sized in metres, with sources cited in the docs (CC0 reference photos from Poly Haven or ambientCG as targets):**
   - `bark`: grain axis, fissure depth and spacing, ridged and warped noise;
   - `moss`: patchiness and height;
   - `leaf`: colour, vein contrast, alpha and translucency;
   - `soil`, `sand` and `grass_ground`.
2. **`material_layer` masks:**
   - `slope` with `angle_min` and `angle_max` (degrees from horizontal, in world space), with a soft edge width;
   - `height` with `z_min` and `z_max` in world metres, soft edged;
   - `up_facing` (moss and snow on top), with a strength;
   - `attribute`, reading a named float attribute such as `slope`, `height` or `curvature` that `heightfield` and `noise_displace` write.
   Masks combine with the existing ones.
3. **`stone` without polygon patches:** find why its cell pattern shows hard polygon edges on curved surfaces (cell distance metric, mapping, or a hard threshold) and fix it, so colour patches have soft, natural boundaries at the default settings, while stone with explicit cells can still be asked for.
4. **Docs and MCP:** the command reference, MCP schemas and `src/mcp/instructions.ts` cover the new presets and masks; before and after renders of `stone` and renders of each new preset go in `docs/materials/` as PNGs.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Each preset builds and bakes.
- Base-colour luminance coefficient of variation is at least 0.15 over a 1 m patch at the default scale for every natural preset (scans measure 0.25–0.40, section 2.6).
- The slope mask is 0 on a flat plane and 1 on a 60° plane with `angle_min` 30; the height mask is 0 below `z_min` and 1 above it beyond the soft edge; `up_facing` is 1 on an upward face and 0 on a downward one.
- The `attribute` mask equals the attribute value written by `heightfield` at sampled points.
- Stone: an edge-softness statistic of the colour-patch boundaries (for example the share of boundary pixels whose luminance step is spread over more than a stated width) separates the new default from the old one on a curved surface; values worked out and justified in the test.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write the methods yourself; do not copy GPL add-ons or article code.
- **Allowed files:** `bridge/blendworks_bridge/presets.py`, new material modules under `bridge/blendworks_bridge/`, existing material helpers (`brass.py`, `marble.py`, `scratches.py`) only if shared code needs it, `commands/materials.py`, `commands/procedural.py`; `src/mcp/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** natural-rules owns `src/judge/**`, `bridge/judge/**`, `schemas/**` and `scripts/**`; scatter owns new placement modules, `instancing.py` and `commands/placement.py`. If you both touch `src/mcp/instructions.ts`, keep the change minimal; the job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that dresses the terrain and rock of `docs/examples/noise_terrain.py` with soil, moss on up-facing slopes and stone without patches, plus a bark-textured log and a leaf card, and reviews the close-ups.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
