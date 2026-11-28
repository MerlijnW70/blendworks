# Job: Check throughput — use the judge's CPUs and memory, safely

`npm run check` takes 28 minutes in the judge sandbox and 20 minutes on Windows. Measured (the job workspace):
- 703 Blender processes run through 2 slots, which are busy 95 % of the time;
- each test process uses only 1 to 2 cores, so on the judge's 4 CPUs a third to a half of the CPU sits idle;
- Blender startup is 1.2–1.6 s per process, or 26–35 % of all Blender work;
- a pre-forked Blender pool hangs, because a warm Blender already runs TBB threads.

Every paid delivery runs the check at least twice, so its length limits the whole project. Make it fast with the same pass and fail results.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Slots from the machine.**
   - The number of Blender slots comes from the CPUs available to the process: the cgroup quota in the judge, and the logical CPUs on the host.
   - The host keeps a stated, lower default because it is shared.
   - `BLENDWORKS_JOBS` still overrides it.
   - Each Blender process gets a `--threads` count that fits the slots.
2. **A memory gate.**
   - The runner records each test file's peak memory: cgroup `memory.peak` in the judge, peak working set on Windows.
   - The runner starts a file only while the sum of the recorded peaks of the running files fits within a stated share of the memory limit.
   - Unknown files are treated as large.
   - The records live next to the existing durations.
3. **Less startup.**
   - Bridge test files that are safe to share run several per Blender process, with a full factory reset between files.
   - A test file can opt out.
   - Judge sandbox runs keep fresh processes.
   - State and reason which files share, and prove that no state leaks between them.
4. **Same results.** The set of tests and their pass/fail results are identical at the old and new settings.

## Targets

- Judge sandbox (4 CPUs, 8 GB): `npm run check` from 27:55 to at most 17 minutes, with no out-of-memory.
- Windows host with `BLENDWORKS_JOBS=4`: from 20:33 to at most 12 minutes.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the slot count follows a faked cgroup CPU quota;
- the memory gate holds back a fake memory-heavy file;
- a deliberate state leak between shared files is caught;
- the per-file pass list is identical at jobs 2 and 4.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes: no skipped or weakened tests, no lowered per-file limits, no tests moved out of the check.
- **Allowed files:**
  - `src/blender.ts`;
  - `scripts/**` (runner, slots, pipeline, bridge runner, container check, timings);
  - the bridge test harness (`bridge/tests/harness.py` and a reset helper);
  - `docker/judge/**`, `test/tooling/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared with other jobs; measure the judge target inside the judge image.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the check in the judge image built from main with the patch:
   - it meets the 17-minute target;
   - its peak memory stays under 8 GB;
   - its per-file results match a run at the old settings.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
