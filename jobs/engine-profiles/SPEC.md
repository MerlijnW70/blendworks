# Job: Engine-target profiles a hirer can pin

Hirers buy assets for an engine. Each engine has conventions an asset must meet to import cleanly, and studios add budgets on top: Unreal (collision prefixes UBX_, UCP_, USP_, UCX_; Nanite supports only opaque and masked materials; DirectX normal maps), Godot (import suffixes such as `-col`, `-convcol`, `-colonly`, `-navmesh`, `-noimp`; OpenGL normal maps), Unity (humanoid avatar bone requirements), USD stages (`upAxis`, `metersPerUnit`, anchored asset paths). Texel density, triangle, material and draw-call budgets are conventions rather than standards, so they must be hirer settings. Add profiles the spec can name and pin, and the commands to meet them.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`target` spec group:** `engine` (`unreal`, `unity`, `godot`, `usd`, `generic`), a profile version pinned by hash in the escrow spec, and overridable budgets (`texelDensity` px/m with a band, triangles per LOD, materials, draw calls, texture sizes); profile files live in the repo with their sources cited and checked by a test.
2. **Rules per profile:** naming and collision conventions, axis and unit, pivot placement, normal-map convention, material model limits (for example no transparency on Nanite meshes), skeleton requirements for humanoids (bone map to the engine's humanoid), lightmap UV channel where the engine expects one, and texel density measured on visible area.
3. **Commands to meet them:** `collision_generate` (box, convex hull, convex decomposition into a capped number of hulls, named per profile), `texel_density` (measure and set by scaling UV islands to a target), `lightmap_uv` (a second non-overlapping UV channel), `normal_convention` (flip green on export when needed), and export presets per engine.
4. **Docs:** a page per engine with what the profile checks and what it cannot check.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include for each engine a fixture that passes and one that fails each rule.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `schemas/**`, new bridge modules and commands for collision, texel density, lightmap UVs and normal convention, the export command module for presets, `src/mcp/**` metadata, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs run one at a time; this one starts after visual-judge-2 lands.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge prepares the crate proof asset for Unreal and for Godot with the new commands, judges each with its profile and sees them pass, and sees the unprepared crate fail the named rules.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
