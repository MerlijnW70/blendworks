# Job: Documentation a new agent or contributor can navigate, and a quickstart that ends in a judged asset

`docs/DESIGN.md` has grown to about 1,000 lines: protocol, MCP server, every command family's contract, asset specs, the judge, determinism, the library, packages and the natural-shape commands, with command contracts in long prose bullets far from the command table. The README quickstart judges a fixture rather than the user's own asset, never says where the workspace is, and covers only Claude Code on one platform. Restructure the docs and write the missing onboarding.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Split:** `docs/DESIGN.md` becomes an architecture overview of about 150 lines (parts, invariants, section map). Content moves, verbatim where possible, to `docs/protocol.md`, `docs/mcp.md`, `docs/commands/README.md` (an index of every command by family) and one file per family under `docs/commands/`, `docs/specs.md`, `docs/specs-natural.md`, `docs/judge.md`, `docs/visual-judge.md`, `docs/library.md` and `docs/packages.md`. Cross-references become relative links. Nothing is lost: a test checks that every command name, every asset-spec rule name and every JSON example block that existed is present in the new tree.
2. **Code and tests that read the docs** (for example `test/judge/texture-rules.test.ts`, `test/judge/natural-templates.test.ts`, strings in bridge modules that cite DESIGN sections, `docs/research/*.md` citations, README and CONTRIBUTING links) are updated, and a test fails when a `@command` is missing from `docs/commands/`.
3. **Stale statements fixed** and, where a number is generated elsewhere, linked to its source rather than restated. The README is the single owner of environment variable defaults.
4. **Quickstart** (`docs/quickstart.md`, linked from the README): from install to the agent building its own asset, exporting it, judging it and revising it; where the workspace is; GPU optional; `--allow-python` and `--workspace`; Windows, WSL and Linux setups (BLENDER paths, running the MCP server in WSL with a Windows client and the reverse); MCP configuration snippets for Claude Code, Claude Desktop, Cursor and VS Code; installing the desktop add-on; judging paid work safely (link to the judge isolation docs); a "write your first spec" walk-through with a prop spec.
5. **Examples index:** `docs/examples/README.md` starts with a table of every example (what it shows, run time, which commands), and every example script is run by a test (add the missing ones at reduced settings).
6. **Public-facing text** contains no private job names or internal escrow references (`jobs/` stays as the job archive).

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail.

## Rules

- Follow `CONTRIBUTING.md`. Do not change behaviour; only docs, doc-reading tests and doc strings.
- **Allowed files:** `docs/**`, `README.md`, `CONTRIBUTING.md`, tests that read docs, doc strings in source that cite DESIGN sections, new example tests under `test/`.
- **Files shared with other open jobs:** every job edits `docs/DESIGN.md`; this job runs when few others are open, rebases last, and carries any section another job added into the new tree.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.
- **While working:** iterate with `npm run check:fast`. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge follows the quickstart on this machine from a fresh clone to a judged asset of its own, and looks up three commands' contracts through the index.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
