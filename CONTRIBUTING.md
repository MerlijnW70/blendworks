# Contributing

Blendworks is built as paid jobs. A job spec in `jobs/<job>/SPEC.md` says what to build; `docs/DESIGN.md` is the contract. The judge pays when `npm run check` passes on a fresh clone with the patch applied and every acceptance item holds.

## Rules

- **Node side:** TypeScript, strict, in `src/`.
- **Blender side:** Python 3 for Blender's bundled interpreter, in `bridge/`. It uses only `bpy`, `bmesh`, `mathutils` and the standard library.
- **Dependencies:** runtime dependencies are `@modelcontextprotocol/sdk` and `zod` only; dev dependencies are only those in `package.json`.
- **Blender binary:** the `BLENDER` environment variable names it. Tests that need Blender use it and run headless, with `--background --factory-startup`.
- **No arbitrary code execution** from bridge commands, except the explicitly gated `run_python`.
- **Code style:** no code comments in TypeScript or Python; clear names instead. Every source file at most 400 lines.
- **Tests:** `test/` (vitest, which may start headless Blender) and `bridge/tests/` (Python tests run inside headless Blender by `npm run test:bridge`). Expected values come from the design or the spec, worked out by hand.

## Delivering

Make one commit with a short title and no body, as a patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
