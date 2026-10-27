# Contributing

Blendworks is built as paid jobs. A job spec in `jobs/<job>/SPEC.md` says what to build; `docs/DESIGN.md` is the contract; `jobs/TEMPLATE.md` is the shape of a new spec. The judge pays when `npm run check` passes on a fresh clone with the patch applied and every acceptance item holds.

## Rules

- **Node side:** TypeScript, strict, in `src/`.
- **Blender side:** Python 3 for Blender's bundled interpreter, in `bridge/`. It uses only `bpy`, `bmesh`, `mathutils`, the `numpy` that Blender bundles, and the standard library.
- **Dependencies:** runtime dependencies are `@modelcontextprotocol/sdk`, `zod` and `gltf-validator` (the Khronos glTF validator, pinned to exactly `2.0.0-dev.3.10`) only; dev dependencies are only those in `package.json`.
- **Blender binary:** `src/blender.ts` is the only place that finds it: the `BLENDER` environment variable, then standard install folders, then `PATH`. Run `npm run doctor` to see what it finds. Tests that need Blender run headless, with `--background --factory-startup`.
- **No arbitrary code execution** from bridge commands, except the explicitly gated `run_python`.
- **Code style:** no code comments in TypeScript or Python; clear names instead. Every source file at most 400 lines.
- **Tests:** `test/` (vitest, which may start headless Blender) and `bridge/tests/` (Python tests run inside headless Blender by `npm run test:bridge`). Expected values come from the design or the spec, worked out by hand.

## Working fast and safely

Blender is heavy, and the owner's PC froze once under parallel load. At most `BLENDWORKS_JOBS` (default 2) Blender processes run at once, across vitest workers, `npm run test:bridge`, builds and fixture generation. A lock in the cache folder enforces it. Do not raise it, and do not run several full checks at once.

| Command | Use |
|---|---|
| `npm run check:fast` | While iterating. Runs the rules, the typecheck, every unit test that needs no Blender, and the Blender and bridge tests related to your changed files. |
| `npm run check` | Once, at the end. The full gate: rules, typecheck, build, all tests, all bridge tests and the add-on build. |
| `npm run test:bridge -- render smoke` | Bridge test files whose name contains an argument. It prints the time of each file and the slowest ones. |
| `npx vitest run test/judge/closeups.test.ts` | One test file. |
| `npm run doctor` | Checks Node, Blender, GPU devices, sandbox tools and the cache. |
| `npm run clean` | Empties the cache folder (`.cache`, or `BLENDWORKS_CACHE`). `-- --all` also removes `dist`. |

`check:fast` compares your tree with the merge base on `main` and picks tests by this mapping:

| Changed | Runs |
|---|---|
| Any change | Rules, typecheck and every test file that does not call `useBlenderSlot()` |
| `src/judge/<name>.ts` | `test/judge/<name>.test.ts`; with no such test, every `test/judge` test |
| `src/mcp/library/<name>.ts`, `src/mcp/<name>.ts` | `test/library-<name>.test.ts`, `test/mcp-<name>.test.ts`; with no such test, the whole family |
| `src/session.ts` | `test/session.test.ts` and `test/mcp-e2e.test.ts` |
| `src/blender.ts`, `scripts/`, `test/setup/`, `package.json` | The tests under `test/tooling` |
| `bridge/blendworks_bridge/**` | The bridge tests of that command (table in `scripts/lib/fast-map.ts`); the core set for other modules |
| `bridge/judge/**`, `schemas/` | Every Blender judge test; the spec test |
| `bridge/tests/test_*.py`, a bridge test helper | That test; the tests that import the helper |
| A test helper under `test/` | The tests that import it |

### Writing tests

- **Blender in vitest:** a test file that starts Blender calls `useBlenderSlot()` from `test/setup/slot.ts` once at the top, before anything else. Each Blender process then holds one slot from its spawn to its exit, never between processes; the setup wraps the shared spawn helpers for this. `test/tooling/guard.test.ts` fails when a file that starts Blender does not.
- **Judge fixtures:** never generate them in a test. A vitest `globalSetup` makes them once per fixture script and Blender version in `.cache/fixtures`. Every `test/judge/fixtures.py` or `test/judge/<name>_fixtures.py` is a fixture set. It receives the assets folder and the markers folder after `--`. Tests call `makeFixtures(name)` or `makeTextureFixtures(name)` from `test/judge/helpers.ts` and get a private copy of the assets, so they may write next to them. Fixtures are generated, never committed binaries.
- **Where tests write:** only under the cache folder (`freshDir` in `test/judge/helpers.ts`) or the OS temp folder, never in a tracked path.
- **Unit tests without Blender:** `BLENDWORKS_FIXTURES=skip npx vitest run <files>` skips fixture generation.
- **Changed behaviour:** existing tests that assert behaviour you changed may be updated. List them in your delivery.

## Delivering

Rebase onto the latest `main`, run `npm ci` and `npm run check` once, and make one commit with a short title and no body, as a patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
