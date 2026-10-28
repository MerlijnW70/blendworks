# Job: L-systems for plants

Herbs, ferns, grasses and flowering plants are described compactly as L-systems: an axiom rewritten in parallel by rules, then drawn by a turtle that pushes and pops its state at `[` and `]`. Blendworks can grow trees by colonisation and levels, but not plants by grammar. Build the `lsystem` command (plan item P8, second half, in `docs/research/natural-shapes.md`), after *The Algorithmic Beauty of Plants* [S1], producing a `blendworks.skeleton` so the tree-mesh step and the natural judge rules can use it.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`lsystem` command:**
   - Parameters: `axiom`, `rules` (bracketed, with optional probabilities for stochastic rules [S1, 1.7] and numeric parameters for parametric rules [S1, 1.10], with conditions), `iterations`, `angle`, `step`, `width`, `width_ratio` (default `1/√2` [S1, page 57]), `tropism` (vector and strength), `seed`, `organs` (object names for leaf, flower or fruit symbols), and the turtle symbols of the book (`F f + - & ^ \ / | [ ] !` and `'` or a documented equivalent).
   - Output: a skeleton in the `blendworks.skeleton` version 1 format (documented in `docs/DESIGN.md`), so `tree_mesh` can mesh it when it exists and the judge can read it; a curve preview like `grow_tree`'s; organs placed through the existing instance machinery at their symbols with the turtle's frame.
   - Hard caps on the string length and on the node count, checked before expansion where they can be, with a clear message.
   - Deterministic by seed; parsing errors name the rule and position.
2. **Presets:** a small, documented library of grammars from the book (for example the bracketed plants of figure 1.24, a stochastic plant, a parametric monopodial tree, a fern-like compound leaf), each cited by section and figure.
3. **Routing, docs and MCP:** `family`, `intents` and `nearest` metadata, held-out benchmark intents without lowering its floors, the command reference, one short clause in `src/mcp/instructions.ts` (it is at its 4096-character limit), and a plant workflow.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

- The derivation string after `n` steps equals hand-worked bracketed examples from [S1] (section 1.6.3), and the segment count matches.
- A parametric rule with a condition gives the hand-worked string for two steps.
- Stochastic rules with a fixed seed are deterministic; over many seeds the rule frequencies match the probabilities within a stated tolerance.
- Turtle geometry: `F+F` with angle 90° gives the hand-worked endpoints; `[` and `]` restore position and frame exactly; `&`, `^`, `\`, `/` and `|` rotate about the right axes.
- Widths follow `width_ratio` at each branching, and the skeleton validates as version 1 (one root, parents before children).
- The string-length cap refuses an exploding grammar before it runs out of memory.
- Fixture assets are generated in headless Blender by a fixture script, never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`. Write from the book; cite sections and figures.
- **Allowed files:** new modules under `bridge/blendworks_bridge/` and `commands/`, the skeleton helpers (`tree_skeleton.py`, `gltf_extras.py`) where reuse needs it, `commands/__init__.py` and `kit_limits.py` minimally; `src/mcp/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**` (new files, or tests whose asserted behaviour changes, listed in the delivery), `docs/**`.
- **Files shared with other open jobs:** tree-mesh owns `tree_mesh` and `tree_leaves` modules; natural-rules-b owns `src/judge/**`, `bridge/judge/**`, `schemas/**`. If several of you touch `src/mcp/instructions.ts` or the benchmark, keep the change minimal; the job that lands later rebases.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs a commands-only script in `docs/examples/` that grows four plants from the presets (a bracketed herb, a stochastic bush in three seeds side by side, a parametric tree, a fern-like leaf) with leaf and flower organs and materials, and reviews the renders: each plant reads as a plant, the stochastic three differ but belong to one species.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
