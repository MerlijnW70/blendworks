# Job: Polish round 1 — install, previews, tidy rollback leftovers, fast tests

The last wave left a list of verified rough edges outside the judge. Fix each one properly, with a regression test.

## Base

- **Base commit:** `24b0f40`. Rebase onto the latest `main` before delivering.

## Required

1. **`npm run install-claude` with `BLENDER` set:**
   - Today `src/mcp/install.ts` builds `claude mcp add -e BLENDER=<path> blendworks -- …`. `-e` takes several values, so the server name is read as an env entry and the command fails with "Invalid environment variable format: blendworks".
   - Build an argument order the Claude CLI parses correctly. Check the CLI's documented syntax with `claude mcp add --help`; do not guess.
   - Test the produced argument vector without running the real CLI, and never modify the user's Claude config in tests.
   - If the CLI's help shows the order is ambiguous for any value, use the form it documents as unambiguous.
2. **Preview lighting for every view:**
   - The `bottom` view (and any view facing away from the key light) renders too dark. The UV checker from below is nearly black.
   - Make the preview light rig follow the camera, or add a fill from the view direction, so that every turntable view and every `focus` direction is evenly lit.
   - Keep `shaded`, `clay`, `normals`, `uv_checker` and `material_id` consistent across views.
   - A test measures mean luminance per view on a neutral grey cube. Every view must be within a stated ratio of the brightest.
3. **Rollback leftovers:**
   - Session-robustness moved rollback to Blender's undo. Remove the now no-op `touch_*` snapshot calls from every command file and the methods themselves, unless something still uses them; prove with tests that rollback still holds.
   - Fold the metadata override table in `bridge/blendworks_bridge/policy.py` into the `@command` declarations of the commands it describes (`mutates`, `destructive`, `destructive_when`, `slow`, `timeout`). The metadata then lives with the command.
   - `test_describe.py` checks that every command declares its metadata, and that no override table remains.
4. **Fast tests:**
   - `bridge/tests/test_uv_texel.py` takes about 34 s, and other bridge tests take seconds. Find out why: profile it, and report the cause.
   - Make it fast without weakening what it checks, for example with smaller meshes that prove the same property, or computing once and reusing.
   - Report before and after times.
5. **Per-process Blender slots:**
   - Today a vitest file that uses Blender holds one slot for its whole run, even while idle.
   - Change `useBlenderSlot` (or its replacement) so a slot is held only while a Blender process runs: acquire at spawn and release at exit. Wrap the shared spawn helpers in the test setup for this.
   - The cap must still hold across processes. Keep and extend the concurrency test.
   - Report the full-check time at `BLENDWORKS_JOBS=2` before and after.

## Tests

- **Install:** the argv for `install-claude` with and without `BLENDER`, matching the CLI's documented syntax. A test fails if the name is placed where `-e` would consume it.
- **Preview luminance:** the per-view luminance ratio holds.
- **Rollback:** the existing rollback fingerprint tests still pass with the `touch_*` calls removed. A test fails if an override table is reintroduced.
- **`test_uv_texel.py`:** it still fails when texel density is computed wrongly. Prove this by breaking the code once.
- **Slots:** with `BLENDWORKS_JOBS=1`, no two Blender processes overlap. A file waiting between processes does not block another file.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:** `src/mcp/install.ts`, `src/mcp/install-claude.ts`, `bridge/blendworks_bridge/**` (except judge code, which lives in `bridge/judge` and is not yours), `bridge/tests/**`, `test/setup/**`, `test/tooling/**`, `scripts/lib/slots.*`, `scripts/lib/run.*`, the tests for these, and `docs/DESIGN.md` sections 1 and 2 where behaviour changes. Existing tests that assert changed behaviour may be updated; list them.
- **Files shared with other open jobs:** judge-integrity edits `src/judge/`, `bridge/judge/` and `test/judge*`. Do not touch those. Rebase onto the latest `main`.
- **Environment and concurrency:** `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe` on this machine; at most `BLENDWORKS_JOBS` (2) Blender processes. Iterate with `check:fast`, and run `check` once at the end at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Each test above fails when its behaviour is broken.
3. The judge runs the produced `install-claude` argv against `claude mcp add --help` semantics by hand, views a bottom-view and focus preview, and compares the full-check timings.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Include the timing tables. Announce its sha256 to the judge.
