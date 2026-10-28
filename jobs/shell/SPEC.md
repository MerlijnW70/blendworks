# Job: Logarithmic shells

Shells are among the clearest natural forms: a generating curve swept along a helico-spiral whose size grows by a constant factor per turn. Blendworks can sweep along circles, arcs and helices, but not along a growing spiral with a growing profile. Build `shell` (plan item P9 in `docs/research/natural-shapes.md`), after Raup's model [S32, S33].

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`shell` command:**
   - Parameters: `name`, `W` (expansion per whorl), `D` (relative distance of the generating curve from the axis), `T` (translation along the axis per whorl), `turns`, `profile` (`circle`, `ellipse` with an aspect, or points in metres), `size` (the final aperture size in metres), `steps` per turn, `ribs` (`count` and `height`), `spiral_ridges` (`count` and `height`), `lip` (a flared thickened rim), `thickness` (a solid wall with an inside), `handedness` (`right`, `left`).
   - The profile is scaled by the same geometric factor as the spiral radius, so the form is self-similar.
   - The apex is closed at an on-axis point as `lathe` does, and the aperture is closed by the lip and the wall, so the result is one closed manifold solid.
   - UVs follow the growth: `u` around the profile, `v` along the spiral in a length-proportional parameter, so a material in metres does not stretch towards the aperture.
   - Shading follows the default-shading rules of `lathe` and `sweep` (flat faces flat, profile corners hard, smooth elsewhere).
2. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference and `src/mcp/instructions.ts`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- The radius ratio between points one whorl apart equals `W` to 1e-9.
- `D` equals the ratio of the inner to the outer distance of the generating circle from the axis.
- The translation per whorl matches `T` relative to the radius.
- The mesh is one closed manifold shell, closed at the apex, with consistent winding and a positive volume; with `thickness` the wall is at least the stated thickness everywhere (sampled).
- Left and right handedness are mirror images.
- UV stretch (the ratio of UV length to world length along `v`) stays within a stated band over all turns.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the papers.
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, `revolve.py`, `skin.py` and `shading.py` where reuse needs it, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** other open jobs own their new command modules; if several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that builds three shells (a conch-like high spire, a flat ammonite-like coil, a ribbed scallop-like form with ribs) with materials, and reviews the renders.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
