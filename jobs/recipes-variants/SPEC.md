# Job: Recipes, seeded variants and best-of-N with judge-and-revert

Procedural tools (Houdini, Geometry Nodes, Infinigen) treat a generator as an editable artefact; Blendworks treats each session as a one-off. Research on Blender agents shows that a library of reusable recipes and a search over candidates with a verifier that can revert both raise quality substantially (SceneCraft's learned function library, BlenderAlchemy's breadth-by-depth search). Make a session replayable as a recipe, run it as seeded variants, and let an agent keep the best of several candidates by the judge's own score.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Journal:** the MCP server records every successful mutating command of a session (name, arguments, reply summary, seed fields) as a recipe file (JSON, versioned) in the workspace; failed and rolled-back commands are recorded as such and skipped on replay. `recipe_save`, `recipe_list`, `recipe_show`.
2. **Replay:** `recipe_run` replays a recipe into an empty scene, with parameter overrides and a seed offset applied to every seed field, and reports any command whose reply differs from the recorded summary (determinism check). Replaying a recipe twice with the same seed gives byte-identical exports (where Blender itself is deterministic; state the exceptions).
3. **Variants:** `blendworks batch <recipe> --seeds N --spec <spec>` (CLI) produces N variants, judges each with the spec, and writes a table of verdicts and key measurements; runs within the slot limits.
4. **Best of N:** a documented agent workflow and a tool (`checkpoint_compare` or similar) that scores K candidate states (saved as checkpoints) with the judge's measured rules and returns the best, so an agent can branch, judge and revert.
5. **Recipe library:** recipes can be stored with a title and tags in a library folder and searched by `blender_find_tools`-style search; the docs examples are exported as recipes.
6. **Docs and MCP:** tools documented, instructions updated through the mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: a recipe recorded from a session replays to an identical export; a seed offset changes seeded outputs and nothing else; a rolled-back command is not replayed; batch judges every variant; best-of-N picks the candidate with the best score on a fixture where the answer is known. No wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** new modules under `src/mcp/` and `src/` (recipe, batch), the session and server wiring needed to record commands, `bridge/blendworks_bridge/commands/checkpoints.py` and a new compare module, `src/judge/cli.ts` only to add the `batch` subcommand entry, `package.json` scripts, `test/**`, `bridge/tests/**`, `docs/**`.
- **Files shared with other open jobs:** judge jobs own the rest of `src/judge/**`; mcp-instructions owns instructions and routing until it lands.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge records a session that builds a rock with the rock commands, replays it, runs 8 seeded variants through `batch` with a natural rock spec, and sees the verdict table and the variants' renders.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
