# Job: Stable tests — no test depends on how busy the host is

Several tests on `main` fail on a busy host and pass alone. Every worker then has to rerun them and explain the failure, which costs time and trust in the check. Make each one deterministic at the root.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **`bridge/tests/test_tree_batch.py::test_the_plan_follows_cpus_memory_and_tasks`.**
   - `workers.plan(6, cpus=8, memory=None)` reads the host's live free memory. Decide what `memory=None` means, either "unknown, do not cap" or an explicit probe, make the API say so, and give the test explicit inputs.
   - A separate test covers the probe path, with an injected probe.
2. **`bridge/tests/test_autosave_bench.py`.** Its overhead target compares wall-clock times across a busy host.
   - Measure overhead in a way that does not depend on host load: CPU time of the process, a work-count, or interleaved paired runs with a stated statistic.
   - Keep the target meaningful. The test must still fail on a real regression (prove it).
3. **`test/session-ready.test.ts`.** It waits on Blender slots and times out or throws NestedSlotError under load.
   - Find the cause: slot budgeting, a nested slot request, or a timeout that counts queue time. Fix it, so that queue time never counts against the test's own budget, as the work clock elsewhere does.
4. **`test/judge/equivalence.test.ts`.** It runs past its work budget under load. Apply the same rule: budgets count work, not waiting.
5. **Audit.** Search the tests for other wall-clock assertions and live host probes (free memory, CPU count, load) and fix the same way, or list them with the reason they are safe.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Also run each fixed test file under artificial load (for example 6 parallel CPU-bound processes) and show it passes.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- **Allowed files:**
  - `bridge/blendworks_bridge/workers.py` (API meaning only);
  - `test/**`, `bridge/tests/**`, `scripts/lib/**` where the test runner's budgets live;
  - `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own, plus the load generators for the proof.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The fixed files pass under artificial load.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
