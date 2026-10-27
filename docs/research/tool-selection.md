# Tool selection for a large toolset

The Blendworks MCP server offers 83 tools (79 bridge commands with `--allow-python`, plus 4 library tools). Their full listing is 198 181 bytes of JSON, which Claude Sonnet counts as 77 223 input tokens (measured with `npm run bench:tools -- --measure-tokens`). A client sends that on every turn. This note collects what the state of the art does about it, what we chose, and what we measured.

## What others do

### Deferred loading and tool search

- **Anthropic's tool search tool** (Claude API). Tools marked `defer_loading: true` stay out of the prompt. The model calls `tool_search_tool_regex_20251119` or `tool_search_tool_bm25_20251119`, gets back `tool_reference` blocks for up to 5 tools by default, and only those definitions are expanded. The client still sends every definition, since the search runs on Anthropic's servers. The docs advise it from 10 tools or 10 000 tokens of definitions, and say that selection "degrades once you exceed 30–50 available tools". [Tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool).
- **The measured effect.** Anthropic reports 77K tokens of definitions dropping to 8.7K, "an 85% reduction". On their MCP evaluation, Opus 4 went from 49 % to 74 % and Opus 4.5 from 79.5 % to 88.1 %. They advise keeping the "three to five most-used tools always loaded". [Introducing advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use), 24 November 2025.
- **Claude Code's deferred MCP tools.** "Only tool names and server instructions load at session start." The model loads definitions with its `ToolSearch` tool. This is on by default; `ENABLE_TOOL_SEARCH=auto` defers only once the definitions reach 10 % of the context window.
  - A server can keep one tool loaded with `_meta["anthropic/alwaysLoad"]`.
  - Server instructions and upfront descriptions are cut at 4 096 characters, deferred ones at 16 384.
  - The search reads descriptions from the start, so the docs advise putting "the words Claude would search for near the start".
  - On `list_changed`, an interactive session fetches the new list, and `-p` and the Agent SDK refresh the tool list.
  - Source: [Claude Code MCP docs](https://code.claude.com/docs/en/mcp), "Scale with MCP tool search".
- **Claude Code's client name.** We checked how Claude Code identifies itself with a throwaway MCP server under `claude -p` (version 2.1.311). The `initialize` request carried `clientInfo` `{"name":"claude-code","title":"Claude Code",...}`. No document states this, so it is our observation.
- **MCP `tools/list_changed`.** A server declares `capabilities.tools.listChanged` and then SHOULD send `notifications/tools/list_changed`, after which the client fetches `tools/list` again. In 2025-06-18 this is a server SHOULD with no client duty ([spec](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)).
  - Client support is uneven. The community matrix in [apify/mcp-client-capabilities](https://github.com/apify/mcp-client-capabilities) marks Cursor, VS Code, Cline and Windsurf, among others, as supporting it. A Cursor forum thread reports that it was [not acted on mid-session](https://forum.cursor.com/t/mcp-notifications-tools-list-changed-not-acted-on-mid-session/161459).
  - The 2026-07-28 revision tightens the rules. A tool list "MUST NOT vary per-connection or as a side effect of other requests on the connection", and the notification only reaches clients that opened a `subscriptions/listen` stream ([spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)).
  - A design that relies on the listing growing after a search is therefore not portable. A stable "call any tool" entry point is.

### Toolsets and dynamic discovery

- **GitHub MCP server toolsets.** `--toolsets` (or `GITHUB_TOOLSETS`) picks groups such as `repos` and `issues`. A `default` set is used when none is given, and `all` enables everything. The README says: "Enabling only the toolsets that you need can help the LLM with tool choice and reduce the context size." [README](https://github.com/github/github-mcp-server).
- **GitHub's dynamic toolsets.** The server had a `--dynamic-toolsets` mode with the meta-tools `list_available_toolsets`, `get_toolset_tools` and `enable_toolset`, which grew the tool list at run time. GitHub removed it on 20 May 2026. The reason: it "was a local-only feature never offered by the remote server", and it carried "a separate config flag ..., a parallel registration path ... three meta-tools". [PR #2512](https://github.com/github/github-mcp-server/pull/2512).
- **The MCP client best practices.** They now describe progressive discovery: a `search_tools` meta-tool, a details step and a single stable `call_tool({name, args})`. They suggest switching to it above a share of the context window, "for example, 1%-5%". [Client best practices](https://modelcontextprotocol.io/docs/2026-07-28/develop/clients/client-best-practices).

### Tool consolidation with action enums

- **GitHub** merged 13 tools into 4, "each consolidated tool supports multiple operations through a single `method` parameter" (`issue_read`, `issue_write`, ...). [Changelog, 29 October 2025](https://github.blog/changelog/2025-10-29-github-mcp-server-now-comes-with-server-instructions-better-tools-and-more).
- **Anthropic** advises grouping actions "into a single tool with an `action` parameter. Fewer, more capable tools reduce selection ambiguity." [Define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools). The "writing tools" post adds that tools "can consolidate functionality" and that namespacing by prefix helps. [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents), 11 September 2025.

### Input examples

- Anthropic's `input_examples` field holds example calls, each validated against the schema. Anthropic reports that "tool use examples improved accuracy from 72% to 90% on complex parameter handling". They cost about 20–50 tokens for a simple example and 100–200 for a nested one. A deferred tool's examples are only expanded when the tool is found ([advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use), [define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)).
- OpenAI notes that examples "may hurt performance with reasoning models" ([function calling guide](https://developers.openai.com/api/docs/guides/function-calling)).

### Description design

- **Anthropic:** "Provide extremely detailed descriptions. This is by far the most important factor in tool performance". A description should say what the tool does, when to use it and when not to, and its caveats ([define tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)). "Even small refinements to tool descriptions can yield dramatic improvements" ([writing tools](https://www.anthropic.com/engineering/writing-tools-for-agents)).
- **OpenAI:** "Aim for fewer than 20 functions available at the start of a turn", and "Use tool search to defer large or infrequently used parts of your tool surface" ([function calling guide](https://developers.openai.com/api/docs/guides/function-calling)).
- **The tension.** Longer descriptions help selection but cost tokens on every turn. Deferral removes that cost for everything outside the core.

### Retrieval: BM25 against embeddings

- **ToolRet** ([arXiv 2503.01763](https://arxiv.org/abs/2503.01763)): 7.6k tasks over a 43k-tool corpus.
  - Without instructions, BM25 reaches nDCG@10 22.3. That is level with bge-large (23.0) and above ColBERT (19.5). The best embedding model reaches 33.8.
  - The authors note that some dense retrievers "even underperform compared to simple lexical-based matching approaches like BM25".
  - Retrieval errors carry through: a weak retriever lowers the downstream pass rate by about 11 points.
- **RAG-MCP** ([arXiv 2505.03275](https://arxiv.org/abs/2505.03275)): retrieving the tool first, with an LLM-based retriever, raised selection accuracy from 13.6 % with every tool in the prompt to 43.1 %, while using about half the prompt tokens. The keyword pre-filter baseline reached 18.2 %. That filter was not a tuned BM25.
- **Tool2Vec** ([arXiv 2409.02141](https://arxiv.org/abs/2409.02141)) embeds a tool as the mean of the queries that used it. That is the idea behind our example intents, applied to a lexical index.
- **Cost.**
  - BM25 over 85 short documents needs no model, no download and no network.
  - It is deterministic, builds in about a millisecond and answers in tens of microseconds here.
  - Embeddings need a model: an API call with a key and the network, or a local model of tens to hundreds of MB plus an inference runtime.
  - CONTRIBUTING allows neither: no new runtime dependency and no network in the server.
  - The evidence above also shows that embeddings do not reliably beat BM25 on tool retrieval without domain training.

## What we chose, and why

1. **A small core set, plus `blender_find_tools` and `blender_call`.** This listing is the default for clients without their own tool search. It is the pattern that the MCP best practices and Anthropic's tool search share, and it works in any client.
   - The core is chosen from data, not taste: build-script call counts, the tuning half of the benchmark, and the workflow steps. It is cut at 40 000 bytes and 12 tools.
   - Anthropic's tool search keeps 3–5 tools loaded. Ours holds 9 tools plus the 2 routing tools, because the build scripts show long runs of a few tools: `assign_material` (18 calls), `sweep` (10), `material_procedural` and `material_layer` (6 each).
   - Today the 9 are `assign_material`, `bake`, `clean_mesh`, `delete`, `export`, `instances`, `material_procedural`, `new_scene` and `sweep`.
   - `material_layer` ranks high but does not fit: its schema alone is 16 KB.
2. **Tools found by search become callable two ways.**
   - The server sends `tools/list_changed` and lists the found tools, for clients that refresh their list.
   - It also offers `blender_call`, a stable entry point that validates the arguments against the real schema. This is for clients that do not refresh, and for the 2026-07-28 rule that a listing must not change as a side effect.
   - We did not copy GitHub's dynamic toolsets. GitHub removed them, and enabling whole families wastes tokens when one tool is wanted.
3. **`--toolsets all|core|<families>`.** This mirrors GitHub's static toolsets.
   - `auto`, the default, picks `all` for `claude-code`. Claude Code already defers every MCP tool and searches it itself, so a second search layer would only add a round trip.
   - In that listing the core tools carry `anthropic/alwaysLoad`.
4. **Local BM25 with weighted fields.** The fields are the name, the family, the description, the example intents, the parameter names and enum values, and the notes of the tools that point at this one. A short synonym list adds a lower weight.
   - The intents follow Tool2Vec's lesson: describe a tool by how it is asked for.
   - The weights were tuned on the tuning split only.
   - We ship no embeddings. They would need a network, a key or a model download, and the held-out top-5 accuracy is already 98.6 %, which leaves too little room to measure a gain.
5. **No consolidation into action enums.** The benchmark shows no confusion that needs a merge.
   - The remaining held-out top-1 misses are mostly multi-step tasks, where the first step is a judgement call. The near-miss pairs are routed at 88.9 % top-1 and 100 % top-5.
   - Merging, say, `uv_unwrap` and `uv_smart_project` into one tool with an `action` would make one schema larger and every call more ambiguous, for no measured gain.
   - No tool was renamed, so no compatibility aliases were needed.
6. **"Instead:" notes instead of longer descriptions.** Every tool description now ends with its nearest alternatives and when to use them, taken from the bridge's `nearest` metadata. This is the "when not to use it" that Anthropic asks for, in about 15 tokens a tool.
7. **Example calls in search results, not in the listing.** Each search result carries a one-line example made from its schema, and a test checks that every example validates. Like Anthropic's `input_examples` on deferred tools, it costs nothing until the tool is found.
8. **Workflows as data.** A `goal` returns a tool sequence and its notes from `src/mcp/routing/workflows.ts`. The server instructions only name the goals, from the same list, so the two cannot drift.
9. **Instructions and descriptions within Claude Code's cut.** Claude Code cuts server instructions and upfront tool descriptions at 4 096 characters, so the critical rules come first: the workspace path, units, `blender_find_tools`, previews and the texture order.
   - The instructions are 2 921 characters with a 200-character workspace path, down from about 5 100 characters before this job.
   - The longest tool description is 355 characters, and every one starts with its search words.

## Measurements

The benchmark is `bench/tool-selection/intents.json`. It was written before any change, and its splits were fixed before any tuning.

- **Intents:** 209, phrased as an agent asks.
  - Every tool except `run_python` is expected at least once.
  - The near-miss intents (67) each name the tool they are easily confused with.
  - The multi-step intents (16) expect a tool sequence.
- **Splits:** 69 intents are held out and were never used for tuning. Every third line went to the held-out split.
- **Probes:** a further 15 `probe` intents are phrased the way the raw `bpy` build scripts work ("Run smart UV project", "Bevel the crate edges with bmesh ops"). They test the `run_python` fallback and were added after the first measurements.
- **Before:** all measurements of "before" run against commit `2291451` with the same bench files.

### Deterministic (`npm run bench:tools`)

| | Before | After |
|---|---|---|
| Tools listed by default | 83 | 11 (9 core + `blender_find_tools` + `blender_call`) |
| Listing size | 198 181 bytes | 41 694 bytes |
| Listing tokens, Claude Sonnet count | 77 221 | 16 269 (−78.9 %) |
| Listing tokens, offline estimate (bytes / 2.6) | 76 223 | 16 036 (−79.0 %) |
| Held-out routing top-1 / top-5 | 59.4 % / 81.2 % | 87.0 % / 98.6 % (60 and 68 of 69) |
| Held-out near-miss top-1 | 59.3 % | 88.9 % |
| Probe routing top-5 | 86.7 % | 93.3 % |
| Search time per query | | mean 0.04 ms, max under 1 ms |

The routing "before" column is plain BM25 over the names and descriptions of the old listing, which is what a client-side search such as Claude's BM25 tool search would see. `all` mode lists 84 tools in 204 976 bytes (79 705 tokens). That is 3.4 % more than before, from the "Instead:" notes.

### End to end with a real model

`claude -p` sees the listing and the server instructions in its system prompt, as JSON, and chooses its first tool call. The flags are the same isolated ones the visual judge uses. No tool runs.

- When the model calls `blender_find_tools`, the bench runs the real search against the real server and shows it the result. It may search at most twice.
- A call through `blender_call` counts as the tool it names.
- The model runs at effort `low`.
- The sample is all 69 held-out intents, and separately the 15 probes. Each "before" and "after" row is a separate run.

| Model, sample | Before | After (default listing) |
|---|---|---|
| Sonnet, 69 held-out: accuracy | 94.2 %, 94.2 % | 95.7 %, 95.7 % |
| Sonnet, near-miss (27) | 27/27, 27/27 | 27/27, 27/27 |
| Sonnet, `run_python` chosen | 0/69, 0/69 | 0/69, 0/69 |
| Sonnet, prompt tokens per task (all rounds) | 80 320 | 39 248, 38 923 |
| Haiku, 69 held-out: accuracy | 94.2 %, 97.1 %, 97.1 % | 97.1 %, 97.1 % |
| Haiku, near-miss (27) | 26/27, 27/27, 27/27 | 26/27, 26/27 |
| Sonnet, 15 probes: accuracy and `run_python` | 80.0 %, 2/15 | 86.7 %, 1/15 |
| Haiku, 15 probes: accuracy and `run_python` | 86.7 %, 0/15 | 100 %, 0/15 |

What this shows, honestly:

- The default listing costs about 79 % fewer tokens per turn. Selection is no worse for it: Sonnet chose correctly a little more often in both runs.
- On the near-miss pairs, Sonnet was already perfect before, so it cannot improve. Haiku's near-miss score moved by one task either way between runs, which is noise.
- The `run_python` fallback did not occur on the held-out tasks before or after. On the probes, which invite a script, Sonnet fell back once instead of twice. That sample is small.
- The runs vary by about ±3 points. Haiku before scored 94.2 % once and 97.1 % twice, with the same code. A single difference of one or two tasks out of 69 is not a result.
- The result files are in `bench/tool-selection/results/` (`before-*`, `after-*`; the first Haiku "before" run is not kept).
- Runs made while developing the routing, before the last three changes below, scored 95.7 % and 91.3 % for Sonnet, and 95.7 %, 97.1 % and 98.6 % for Haiku (`all` mode, 98.6 %). Each Sonnet miss in the 91.3 % run was read. Three came from searches the model narrowed to a wrongly guessed family, and one from a `blender_call` nested in `blender_call`. That led to three changes:
  - The family filter now also shows better matches from outside the chosen families.
  - Nested calls are unwrapped.
  - Two families were renamed (`selection` to `faces`, `geometry` to `from_data`).
- A fourth change keeps `run_python` from ranking first in a search. We checked all 431 queries recorded in the final runs: the change alters only 3, all of them probe queries, so it does not affect the held-out runs.
- After the instructions were cut to fit 4 096 characters, a 10-task Sonnet run on the held-out split (`after-revision.json`) scored 10/10, the same as all four earlier runs on those 10 tasks. It used 34 294 prompt tokens per task.
- Argument validity on the first call fell from 91–100 % to 93–96 %. A call through `blender_call` that skipped the search has to guess its arguments. A refusal returns the schema, so the next call can be right.

## How to reproduce

```sh
npm run bench:tools                                   # listing sizes and routing, deterministic, starts Blender once
npm run bench:tools -- --measure-tokens               # also counts the listing tokens with claude -p
npm run bench:tools -- --modes core --e2e 10          # a short end-to-end sample (Sonnet, effort low)
npm run bench:tools -- --modes core --model haiku --split probe --e2e 15
```

`npm test` holds the deterministic numbers as thresholds in `test/mcp-routing-bench.test.ts`:

- held-out top-5 at 68 of 69 and top-1 at 60 of 69;
- a core listing of at most 16 500 estimated tokens and at most 30 % of the full listing;
- a search time under 20 ms.
