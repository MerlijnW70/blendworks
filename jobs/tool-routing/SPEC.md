# Job: Agents find the right Blendworks tool fast

The MCP server lists about 85 tools (81 bridge commands plus the library tools), each with its full schema, and the number keeps growing. Agents pay for every schema in context on every turn, pick near-miss tools (`transform` against `transform_selection`, `uv_unwrap` against `uv_smart_project`, `add_material` against `material_procedural`), and fall back to `run_python` when they cannot find the right one. Make tool selection measurably more accurate and cheaper, for any MCP client, not only one that has its own tool search.

## Base

- **Base commit:** 10942d8. Rebase onto the latest `main` before delivering.

## Required

1. **Research first:** write `docs/research/tool-selection.md`, with sources, covering what the state of the art does about large toolsets, and choose with reasons. Cover at least:
   - deferred loading and tool search: Anthropic's tool search tool, Claude Code's deferred MCP tools, and the MCP `tools/list_changed` notification;
   - toolsets and dynamic toolset discovery, for example the GitHub MCP server;
   - tool consolidation with action enums;
   - input examples;
   - description design;
   - retrieval: BM25 and embeddings, and the cost of each.
2. **Selection benchmark,** built before any change:
   - `bench/tool-selection/`: at least 120 task intents written as an agent would phrase them, each with its expected tool or tools and acceptable alternatives, covering every tool family.
   - Include near-miss pairs and multi-step tasks.
   - Include a held-out split that is not used for tuning.
   - Measure, before and after:
     - the token size of the tool list the client receives;
     - routing accuracy (top-1 and top-5) for the search or router;
     - end-to-end selection accuracy with a real model, using the claude-code provider as the visual judge does (`claude -p`, isolated, no tools executed), on a stated sample size;
     - the `run_python` fallback rate.
3. **Progressive disclosure** that works in any MCP client:
   - The default is a small core set that is always listed, plus `blender_find_tools`, which searches by intent and returns the top matches with their full schemas and a one-line example call each. The core set is chosen from data: frequency in the benchmark and in the proof-asset build scripts.
   - Tools found by search become callable. Use `tools/list_changed` where the client supports it, and a stable fallback where it does not, for example a `blender_call` tool that takes a tool name and its arguments and validates against the real schema.
   - Document the trade-off.
   - An option `--toolsets all|core|<families>` keeps the full listing for clients that prefer it. It is the default when the client already has its own tool search, if that can be detected; otherwise it is documented.
4. **Search quality:**
   - Local and deterministic: no network and no API key needed. For example BM25 over names, descriptions, parameter names, synonyms and example intents, with optional embeddings only if they measurably add accuracy and ship offline.
   - Search completes in under 20 ms per query.
   - Tool families are derived from the bridge command metadata, not a hand-kept list that can drift. A test fails when a new command has no family or no example intent.
5. **Better descriptions:** every tool description says when to use it and when not to, and names its nearest alternative ("use X instead when ...").
   - Keep descriptions short; the benchmark decides.
   - Merge or rename tools only where the benchmark shows confusion, and keep compatibility aliases for one release.
6. **Workflow hints:** `blender_find_tools` also accepts a goal, such as "engraved brass dial" or "rock set", and returns the tool sequence from `src/mcp/instructions.ts`, kept as data in one place so it cannot drift.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- Routing accuracy on the held-out split stays at or above the reported value, as a CI threshold. The test is deterministic.
- Every bridge command has a family, example intents and a near-alternative note.
- A tool found through search is callable in both client modes, and the arguments are validated against its real schema.
- The token size of the core listing stays at or below the reported budget.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:**
  - `src/mcp/**` (see shared files below);
  - new `src/mcp/routing/**`, `bench/**`, `test/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`, `package.json` scripts;
  - the command description and metadata fields in `bridge/blendworks_bridge/commands/*.py`: descriptions only, no behaviour.
- **Files shared with other open jobs:** modeling-3 adds commands and parameters in `bridge/blendworks_bridge/**` and edits `src/mcp/instructions.ts` and schemas. judge-onepass owns `src/judge/**`. The job that lands second rebases. Your family and example metadata must then cover any commands modeling-3 added.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once. Run the end-to-end model benchmark at a small, stated sample, because it uses the user's subscription.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Before and after numbers: the listed-tool tokens at least 70 % lower in the default mode; held-out top-5 routing accuracy of at least 95 %; end-to-end selection accuracy not lower than before, and higher on the near-miss pairs; a lower `run_python` fallback rate.
3. The judge runs `npm run bench:tools` and reproduces the deterministic numbers. It also runs a short end-to-end sample itself.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
