# Job: MCP instructions and core listing that scale with the command set

The MCP server's instructions are capped at 4096 characters (`test/mcp-routing.test.ts`, with a 200-character workspace path) and are now at about 4090: every new command has to squeeze other wording, and parameter detail (materials, scratches, masks) sits there although tool descriptions have 16,384 characters each. The core tool listing for non-Claude-Code clients is `CORE_RANKING`, which the benchmark test requires to equal a ranking derived from tune intents and workflow steps on all 24 positions; ranks 10 to 14 lie within 0.012 of each other and one workflow step is worth 0.011, so any change reshuffles the cut at 12 (`library_apply` fell out). Workers now avoid tune intents to keep the core stable. Replace both with designs that scale.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Tiered instructions:** a pure `buildInstructions(workspace, budget)` assembles Tier 0 (mandatory: workspace, units, `blender_find_tools` and `blender_call`, the preview habit, checkpoints and timeouts, texture order, using shape tools rather than raw geometry; at most about 1,500 characters) and Tier 1 (one short line per command family, by priority) until the budget minus the workspace path is used, and ends by pointing at `blender_find_tools` for the rest. Tier 1 lines are declared next to the command metadata (for example an `instruction=(priority, text)` field on `@command` or on the family table), so a new command adds its line where it is defined.
2. **Goal list through the router:** the inline list of all workflow goals is replaced by a few headline goals plus `blender_find_tools` serving the full list (for example `goal="list"`); parameter detail moves into tool descriptions and workflow notes.
3. **Pinned core:** `CORE_PINNED` (an ordered list of about 8 to 10 stable tools, `library_apply` included) plus a data fill up to the core size from the derived ranking. The test compares the chosen core as a set and the fill against the ranking, not all 24 positions. A generator (`npm run bench:core -- --write`) swaps a fill member only when the score gap exceeds a stated hysteresis, and the test failure tells the worker to run it. Ranking sources use fixed denominators, so adding one workflow step does not rescale the others.
4. **Benchmark:** held-out top-5 and top-1 results do not drop; report before and after.
5. **Generated numbers in docs:** the counts and sizes `docs/DESIGN.md` quotes (tools, intents, held-out, instruction length, listing tokens) are printed by `npm run bench:tools` and checked by a test, so they cannot go stale.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: Tier 0 always fits with a 200-character path; the total never exceeds 4096; a dropped Tier 1 line is reported by name; pinned members are always in the core; a one-step workflow change does not change the core unless the gap exceeds the hysteresis.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** `src/mcp/instructions.ts`, `src/mcp/routing/**`, `bench/tool-selection/**`, command metadata in `bridge/blendworks_bridge/registry.py` and the `@command` blocks (metadata only), `test/mcp-routing*.test.ts`, `docs/**`.
- **Files shared with other open jobs:** rig-animation and bridge-budget may add or change commands; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge adds a dummy command with a Tier 1 line and two workflow steps in a scratch branch and sees the instructions stay within budget, the core unchanged, and the docs-numbers test name the stale figure.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
