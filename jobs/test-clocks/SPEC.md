# Job: No test depends on how fast the machine is

`scripts/lib/wall-clock-lint.ts` refuses upper time bounds in tests, but five files are still allowed to keep them (`WALL_CLOCK_ALLOWED`): `test/mcp-connection.test.ts`, `test/mcp-long-calls.test.ts`, `test/mcp-routing-bench.test.ts`, `test/judge/sandbox.test.ts` and `test/package/native-run.test.ts`. Some also read `Date.now()`, which steps backwards inside the Docker Desktop VM. In the judge image, under load, such bounds fail good work at random (`test/mcp-desktop.test.ts` did, and was fixed on `main` by measuring a monotonic lower bound only).

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Every allowed bound removed by testing the behaviour instead:** for each bound, state what it protects (for example "the client gives up after the configured timeout", "a long call keeps the connection alive", "the routing query is cheap") and test that directly: with an injected or fake clock, by counting work (calls, rows scanned, bytes), by ordering of events, or by a monotonic lower bound where only "not earlier than" matters.
2. **The allowlist is empty and stays empty:** `WALL_CLOCK_ALLOWED` is removed; the lint also refuses `Date.now()` differences in tests (monotonic clocks only) and upper bounds written through helpers or constants, with its own negative test.
3. **No behaviour lost:** each removed bound's purpose is still covered; list old assertion → new assertion.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. No wall-clock bounds.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image).
- **Allowed files:** the five test files above, `scripts/lib/wall-clock-lint.ts`, `test/tooling/**`, `src/mcp/**` and `src/package/**` only to inject a clock, `docs/**`.
- **Files shared with other open jobs:** starts after bridge-budget lands (it changes `test/mcp-long-calls.test.ts`).
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. `WALL_CLOCK_ALLOWED` no longer exists and the lint passes.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
