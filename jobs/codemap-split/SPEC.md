# Job: Code map split — an index plus one map per area

`docs/CODEMAP.md` has reached its 85 KB limit. The next job that adds modules fails the map test: meadow-structure is blocked on it now. A single map of about 21k tokens is also more than a worker should read to find one module. Split it into an index and per-area maps so that a worker reads the index plus the one area they need.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Index.**
   - `docs/CODEMAP.md` becomes a short index, at most 12 KB.
   - It keeps the layer overview and the "how to work" section.
   - It lists each area with one line and a link to its map, and gives a lookup table from command name to area map.
2. **Area maps.**
   - `docs/codemap/<area>.md`, one per cohesive area. For example: MCP server and judge; bridge core (handler, schema, limits, autosave); shapes and modelling; materials and texturing; terrain, rock and liquids; vegetation and ground cover; sky, weather, atmosphere and render; animation and rigging; scripts, bench and tests tooling.
   - The areas are derived by rule (module name prefixes or a stated table), so a new module lands in an area automatically, or the test names the module that has no area.
   - Each area map has the same per-module content as today.
3. **Limits.**
   - Each area map stays under a stated size, for example 20 KB.
   - When an area grows past it, the test fails with a message that says to split that area, not to trim descriptions.
4. **Kept in sync.** The existing stale-map, docstring and size tests cover the index and every area map.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Allowed files:** `scripts/codemap.mjs`, `scripts/lib/codemap.ts`, `docs/**`, `test/tooling/**`.
- **Environment and concurrency:** the machine is shared.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. With meadow-structure's patch (the job workspace) applied on top and the maps regenerated, the map tests pass.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
