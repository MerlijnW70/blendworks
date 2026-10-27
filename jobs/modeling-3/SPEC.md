# Job: Engraving, booleans and materials that hold up on real assets

The armillary-v2 proof asset was the first one built with Blendworks commands only, and it exposed seven tool gaps. Its builder had to work around each of them, and the visual judge scored its materials at 0.55. Close every gap at its root, so that a commands-only build of an engraved, multi-part brass and marble object succeeds on the first try.

## Base

- **Base commit:** 3c16861. Rebase onto the latest `main` before delivering.

## Required

1. **Engraving that survives many cuts:** `engrave` on a single mesh succeeds for at least 40 successive cuts, including 24 glyphs and 360 tick marks around a ring.
   - Today it fails after 4–5 cuts, because latent slivers build up that `clean_mesh` cannot remove. Find the cause (solver, cutter topology, merge distance or face order) and fix it there. Retrying or skipping failures is not a fix.
   - After every cut the mesh is manifold where it was manifold before, has no zero-area or sliver faces (by a stated area and aspect threshold), and gives every face non-zero tangents.
   - New faces get UVs that continue the surrounding mapping, with no unmapped faces and no seams beyond the cut outline.
2. **Tick marks and angular patterns:**
   - `repeat`, or a new command, places copies over an angular range with a step or count, for example 0–90° every 1° with a major mark every 10°.
   - It supports mirroring per quadrant and length or depth per mark class.
   - It can engrave in one boolean pass, so 360 marks are not 360 separate cuts.
3. **Booleans on engraved parts:** an exact union of engraved parts succeeds, or the command picks a solver by a measured criterion and reports which one it used and why. A solver fallback without a reported reason is not acceptable.
4. **Sweeps:** `sweep` accepts `closed=True` with circle and arc paths, producing a closed solid with no seam gap.
5. **Materials that read as real:**
   - The marble preset shows layered, soft-edged veins with natural branching at physically plausible scale, not crack lines or a faint wash. Use reference photos from a CC0 library such as ambientCG or Poly Haven as the target, and cite them in the docs.
   - Brass gets ageing control (new, handled, aged with patina in recesses, dull) driven by curvature or ambient occlusion, so engraved recesses darken.
   - Before and after renders of both presets go in `docs/materials/` as PNGs.
6. **Docs and MCP:** the command reference and MCP tool schemas cover the new parameters, and `src/mcp/instructions.ts` stays accurate.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- 40 successive engrave cuts on a ring; assert manifoldness, a sliver count of 0, no zero tangents and full UV coverage of the new faces.
- 360 tick marks with majors every 10°; assert count, angles and depth classes from the mesh.
- An exact union of two engraved parts, or a solver report with the measured reason.
- A closed sweep on circle and arc paths gives a watertight solid.
- Marble and brass: a measured texture statistic that separates veins from cracks (for example the vein width distribution, or the edge softness of the vein mask), and recess darkening on brass (mean albedo in recesses against open faces). Values are worked out and justified in the test.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:**
  - `bridge/blendworks_bridge/**`, except `commands/uv_pack.py`, `uvlayout.py` and `texel.py`;
  - `src/mcp/**`, `test/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** the judge-speed job owns `commands/uv_pack.py`, `uvlayout.py`, `texel.py`, `src/judge/**` and `bridge/judge/**`. If you must touch `commands/__init__.py` or `chain.py`, keep the change minimal; the job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script, included in `docs/`, that engraves 24 glyphs and 360 ticks on a brass ring, unions it with a second engraved ring, and applies aged brass and marble. It must run without a workaround, and the judge reviews the close-up renders.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
