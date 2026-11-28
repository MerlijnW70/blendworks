# Contributing

Blendworks is built as paid jobs. A job spec in `jobs/<job>/SPEC.md` says what to build; `docs/DESIGN.md` is the contract; `jobs/TEMPLATE.md` is the shape of a new spec. The judge pays when `npm run check` passes on a fresh clone with the patch applied and every acceptance item holds.

## Rules

- **Node side:** TypeScript, strict, in `src/`.
- **Blender side:** Python 3 for Blender's bundled interpreter, in `bridge/`. It uses only `bpy`, `bmesh`, `mathutils`, the `numpy` that Blender bundles, and the standard library.
- **Dependencies:** runtime dependencies are `@modelcontextprotocol/sdk`, `zod`, `gltf-validator` (the Khronos glTF validator, pinned to exactly `2.0.0-dev.3.10`), `@anthropic-ai/sdk` (the official Anthropic SDK for the visual judge, pinned to exactly `1.3.0`) and `gltfpack` (meshoptimizer's WebAssembly build, pinned to exactly `1.3.0`) only; dev dependencies are only those in `package.json`.
- **Blender binary:** `src/blender.ts` is the only place that finds it: the `BLENDER` environment variable, then standard install folders, then `PATH`. Run `npm run doctor` to see what it finds. Tests that need Blender run headless, with `--background --factory-startup`.
- **No arbitrary code execution** from bridge commands, except the explicitly gated `run_python`.
- **Code style:** no code comments in TypeScript or Python; clear names instead. Every source file at most 400 lines.
- **Tests:** `test/` (vitest, which may start headless Blender) and `bridge/tests/` (Python tests run inside headless Blender by `npm run test:bridge`). Expected values come from the design or the spec, worked out by hand.

## Working fast and safely

Blender is heavy, and the owner's PC froze once under parallel load. At most `BLENDWORKS_JOBS` (default 2) Blender processes run at once, across vitest workers, `npm run test:bridge`, builds and fixture generation. A lock in the cache folder enforces it, and hands the slots out first come, first served. Do not raise it, and do not run several full checks at once.

| Command | Use |
|---|---|
| `npm run check:affected` | While iterating and before merging. Runs the rules, the typecheck, the builds, every unit test that needs no Blender, a core set, and the Blender and bridge tests your changes can affect (`check:fast` is the same). |
| `npm run check` | Once, at the end. The full gate: rules, typecheck, build, all tests, all bridge tests and the add-on build, run side by side; the first failure stops the others. No test reads the build output. It ends with the slowest files, the time each spent waiting for a Blender slot, and how busy the slots were; the full log is in `.cache/timings`. |
| `npm run check:stress` | The full check three times in a row while a CPU and Blender load runs beside it (below). |
| `npm run durations` | Saves the file times of your last check to `scripts/durations.json`, which orders the heaviest test files first on a fresh clone. A file without an entry is scheduled first and fails nothing. `npm run check` refreshes the file by itself when it passes on a clean `main`, and prints which files had no entry; the refresh also drops entries of deleted files. Do not edit it in a job. |
| `npm run test:bridge -- render smoke` | Bridge test files whose name contains an argument. It prints the time of each file and the slowest ones. |
| `npx vitest run test/judge/closeups.test.ts` | One test file. |
| `npm run doctor` | Checks Node, Blender, GPU devices, sandbox tools and the cache. |
| `npm run clean` | Empties the cache folder (`.cache`, or `BLENDWORKS_CACHE`). `-- --all` also removes `dist`. |

`check:affected` (and its alias `check:fast`) compares your tree, untracked files included, with the merge base on `main` (`-- --base <ref>` for another), prints each changed file with the tests it selects and why, and runs the rules, the typecheck, both builds and the selected tests; `-- --dry-run` only prints the selection. It picks tests by a dependency graph of the repository, not a table:

| Changed | Runs |
|---|---|
| Any change | Rules, typecheck, builds, every test file that does not call `useBlenderSlot()`, and the core set: `test/mcp-e2e.test.ts`, `test/session.test.ts`, `test/tooling/codemap.test.ts` (it reads the whole tree), `bridge/tests/test_smoke.py`, `test_describe.py`, `test_crate.py` |
| A TypeScript file | Every test that imports it, directly or through other modules |
| A bridge module, only inside bodies of functions that do not run while modules load | The tests that call one of its commands, directly or through modules that import it, or import it themselves |
| A bridge module at module level (or a function the module code reaches) | Every test that loads the bridge handler, since the handler loads every command module |
| Native code under `native/` | The tests that call the modules that load its library (`terrain_core.py`): the terrain kernel tests |
| An example script, a doc, a data file, a judge or package script | The tests that name it by path or file name, or run it |
| Shared infrastructure: `package.json` and the lock file, `tsconfig*.json`, `vitest.config.ts`, `docker/`, `test/setup/`, the bridge harness, the runner in `scripts/`, `src/blender.ts`, the bridge handler, registry, schema, limits and command package, `schemas/`; a deleted or renamed file; a data file no test names | Everything |

A change inside one module selects little: a body change in `bridge/blendworks_bridge/stone_shape.py` selects 4 Blender vitest files and 5 bridge test files (about 25 s of Blender work), one in `tree_bark.py` about 160 s, one in `src/mcp/results.ts` about 70 s, besides the unit tests that need no Blender (about 44 s). A change that touches shared infrastructure runs everything, as long as the full check. `npm run study:mutation` proves the selection safe (see section 5 of `docs/DESIGN.md`), and `npm run check:watch` keeps running the full check on each new `main` commit in the background.

### Writing tests

- **Blender in vitest:** a test file that starts Blender calls `useBlenderSlot()` from `test/setup/slot.ts` once at the top, before anything else. Each Blender process then holds one slot from its spawn to its exit, never between processes; the setup wraps the shared spawn helpers for this. `test/tooling/guard.test.ts` fails when a file that starts Blender does not.
- **Judge fixtures:** never generate them in a test. A vitest `globalSetup` makes them once per fixture script and Blender version in `.cache/fixtures`. Every `test/judge/fixtures.py` or `test/judge/<name>_fixtures.py` is a fixture set. It receives the assets folder and the markers folder after `--`. Tests call `makeFixtures(name)` or `makeTextureFixtures(name)` from `test/judge/helpers.ts` and get a private copy of the assets, so they may write next to them. Fixtures are generated, never committed binaries. A script starts with `FIXTURE_DEPS = (...)`, the bridge or judge files it imports (`"bridge/blendworks_bridge"` for the whole bridge, `"bridge/judge/judge_font.py"` for one judge module, `()` for none); its cache key hashes the script, those files and the Blender version, nothing else, and `test/tooling/fixture-deps.test.ts` fails when a script imports a module its `FIXTURE_DEPS` does not cover, and names the line to put first in that script. A cache hit refreshes the entry's age, and pruning never removes an entry that is locked or in use.
- **Where tests write:** only under the cache folder (`freshDir` in `test/judge/helpers.ts`) or the OS temp folder, never in a tracked path.
- **Timeouts are work budgets:** in a file that calls `useBlenderSlot()`, give a `describe` or `it` its budget with `workBudget(ms)` and wrap a hook as `beforeAll(withWorkBudget(ms, fn))`, both from `test/setup/work-clock.ts`. The budget counts only work: time spent waiting for a Blender slot or a lock does not count, and waiting has its own bound of 45 minutes per test. A test that overruns fails with `timed out working` or `timed out waiting`, its stage and its name. `test/tooling/guard.test.ts` fails on a plain vitest timeout in such a file.
- **Test render profile:** vitest sets `BLENDWORKS_TEST_RENDER=test` and `BLENDWORKS_DEVICE=cpu`. The judge then renders its views at 128 px with 4 samples on the CPU: judging the crate fixture with six views takes 3.4 s instead of 5.0 s, because the GPU probe and full-size views dominate small test assets. Only `src/judge/render-profile.ts` reads the variable; without it the judge renders 512 px with 24 samples, as always. A test that needs the GPU path passes `device`. Assert on what the renders show, never on their pixel size.
- **Load-independent tests:** a test must pass on a machine that other agents are loading. Never assert that something took less than some milliseconds (`test/tooling/wall-clock-lint.test.ts` refuses new `toBeLessThan(<time>)` bounds outside its allow-list). Instead: order events by a barrier, such as a file or ticket appearing, with `waitFor(condition)` from `test/setup/wait-for.ts`; let the process that holds something report its own release time and compare against it; inject a fake clock (`useTimers` in `test/setup/work-clock.ts`); or assert a deterministic count that makes the time (packs, polls, calls). A lower bound on time is fine.
- **Unit tests without Blender:** `BLENDWORKS_FIXTURES=skip npx vitest run <files>` skips fixture generation.
- **Changed behaviour:** existing tests that assert behaviour you changed may be updated. List them in your delivery.

### Stress

`npm run check:stress -- [--runs n] [--cpu threads] [--blenders n] [--device auto|cpu] [--samples n] [--resolution px]` runs the full check `n` times (3) while `threads` busy threads (a quarter of the cores) and `n` Blender processes (2) that render a Cycles scene in a loop run beside it, outside the check's slots, as other agents on the machine would. It passes only when every check passes.

## Delivering

Rebase onto the latest `main`, run `npm ci` and `npm run check` once, and make one commit with a short title and no body, as a patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
