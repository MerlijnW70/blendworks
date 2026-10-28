# Job: A check that starts reliably under the judge's process limit

Inside the judge image (Solive's Docker sandbox: 4 CPUs, 8 GB, a limit of 256 processes), `npm run check` sometimes fails within two seconds: vitest reports "No test files found" and then crashes while printing the error ("code.charCodeAt is not a function"). With the stack trace limit lowered, the real error is `EAGAIN` / `ERR_WORKER_INIT_FAILED`: vitest's worker threads cannot start because every phase (rules, typecheck, build, build:addon, test, test:bridge with its Blender processes and their threads) starts at the same moment under the process limit. It happened on 2 of 3 runs of plain `main` in the image and once on Windows. Separately, `test/session-ready.test.ts` fails under load in the image (an MCP request timeout followed by a slot error). A paid judge must not fail good work at random.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Root cause and fix of the startup failure:** count the processes and threads each phase starts (Node workers, Blender and its `--threads`, tsc, bridge runner), and make the check stay within a stated budget below the container's process limit by construction (for example staggered phase starts, a process budget shared between phases, worker counts derived from the limit, Blender thread counts derived from the CPU count), rather than by retrying.
2. **Real errors surface:** when the test runner fails to start, the check prints the underlying error (not the crash of the error printer) and exits as an infrastructure failure the judge entry can map to "retry" only if the cause is genuinely environmental; a failure caused by the delivery stays a fail.
3. **`session-ready` under load:** root-cause the request timeout and slot error and fix them in the code or the test, whichever is wrong, without wall-clock bounds.
4. **Proof:** ten consecutive full checks of `main` inside the judge image, each started from a fresh container, all pass; report each run's peak process count and the longest quiet gap.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail (for example run the check under a deliberately low process limit and show it stays within budget, or fails with the real error named).

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image).
- **Allowed files:** `scripts/**`, `test/setup/**`, `test/tooling/**`, `test/session-ready.test.ts`, `src/session.ts` and `src/blender.ts` only for thread and process counts, `vitest.config.ts`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`; Docker Desktop for the image. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the check ten times in fresh containers and sees ten passes.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
