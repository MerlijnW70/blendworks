# Job: Polished marble that stays flat, brass scratches that follow the part, and a working install with BLENDER

The engraved-rings acceptance build of modeling-3 showed two material faults on close-ups, and the Claude Code installer still breaks when a Blender path is given. Fix each at its root.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Polished marble is optically flat:**
   - Today the `marble` preset applies a 0.3 mm vein bump by default. On a polished plinth this makes the specular highlight wobble like a lumpy surface (see the `marble-plinth` close-up of `docs/examples/engraved_rings.py`), while polished stone is flat to well under the wavelength of visible light at this scale.
   - Tie relief to finish: a `finish` (or `polish`) parameter, where `polished` gives no relief from the veins and a honed or rough finish may give a small, documented one. The default is polished. Veins, layering and colour stay as they are.
2. **Brass scratches follow the part:**
   - Today the fine scratches are straight lines along one object axis (`scratch_direction` default `x`). On a ring they read as parallel streaks across the curve (see the `whole` and `marble-plinth` close-ups) rather than wear that follows how the part was handled or turned.
   - Add a direction that follows the surface: along the UV `u` direction, or around a given axis (circumferential, as on a turned or polished ring), and make the default fit the common case, documented. Keep the existing axis directions for flat stock.
3. **`npm run install-claude` with a Blender path works with the real Claude Code CLI:**
   - Today `planInstall` builds `claude mcp add blendworks --scope user -e BLENDER=<path> -- node …`. Check how the installed `claude` actually parses that (its `-e` option takes values), and fix the call so the server is registered under the name `blendworks` with `BLENDER` set, for example with option order or `claude mcp add-json`.
   - Verify against the real CLI on this machine without changing the user's own configuration: use a temporary `HOME`/`USERPROFILE` or the CLI's project scope in a temporary folder, then read the entry back (`claude mcp get blendworks`) and check the name, command, arguments and env.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Polished marble: render or bake the normal of a flat polished marble plane; the angle between the shading normal and the face normal stays under a stated bound (worked out from what is visible at 1 m with a 512 px view) everywhere; a honed finish exceeds it.
- Brass on a ring with the surface-following direction: the dominant orientation of the scratch mask, measured in the ring's tangent frame, is within a stated angle of the circumferential direction at sample points around the ring; the axis-aligned direction fails the same test.
- Installer: a unit test of the planned argument list, plus a test against the real `claude` binary when it is on `PATH` (skipped, with the skip visible in the summary, when it is not) that registers into a temporary configuration and reads back name, command, arguments and `BLENDER`.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`.
- Never write to the user's real Claude Code configuration.
- **Allowed files:** `bridge/blendworks_bridge/marble.py`, `brass.py`, `scratches.py`, `presets.py`; `src/mcp/install.ts`; `test/**` and `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery); `docs/**`.
- **Files shared with other open jobs:** noise-terrain owns new bridge command modules, `src/mcp/**` apart from `install.ts`, and `bench/**`; natural-rules owns `src/judge/**` and `bridge/judge/**`. The job that lands second rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge reruns `docs/examples/engraved_rings.py` and reviews the `whole`, `union-joint` and `marble-plinth` close-ups against the ones from before, and registers the server with a Blender path into a temporary configuration.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
