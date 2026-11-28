# Job: Autosave off the request path — a journal and budgeted snapshots

The bridge saves the whole scene to a .blend before every slow command, so it can recover after a crash. Measured on a landscape build (the job workspace):
- autosave is 22–25 % of build wall time at medium size and 48 % at full size (891 of 1841 s for a 2.15 GB scene);
- on the judge it costs about 1 s of CPU per GB per save, and keeps two copies of the scene in the 8 GB sandbox's tmpfs;
- the cost grows with the number of calls times the scene size.

Turning autosave off changes no geometry. Make crash recovery cost almost nothing on the request path, with the same recovery guarantees.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **A journal.**
   - Each successful mutating request is appended to a journal next to the last snapshot, together with the content hashes of the workspace files it read.
   - The journal is flushed before the reply is sent.
   - Failed or refused requests are not journaled.
   - Read-only requests are not journaled.
2. **Budgeted snapshots.**
   - A full .blend snapshot is taken only:
     - when the bridge is idle (no request for a stated time);
     - or when the estimated replay cost of the journal passes a stated multiple of the last snapshot's cost;
     - or before a request that cannot be replayed. Examples: `run_python`, imports from files that changed since they were journaled, `load_blend`.
   - Slow commands no longer force a save.
   - One snapshot is kept, written to a temporary file and swapped in atomically.
3. **Recovery.**
   - After a crash, timeout or cancel, the bridge loads the snapshot and replays the journal.
   - The scene it reaches must be the same as before the crash.
   - A journaled request whose input file changed since it was journaled is reported, and the bridge does not replay it silently.
   - The result says what was restored and how.
4. **Limits.** The snapshot interval, the idle time, the replay budget and the journal size are named limits with stated reasons.
5. **Working with what exists.**
   - Undo, checkpoints and `restore_checkpoint`, `load_blend`, `save_blend`, and session restart keep working.
   - The memory high-water mark of autosave in the judge is at most one copy of the scene.

## Targets

On the scene-speed benchmark scene (`bench/scene-speed`):
- autosave and journal together add at most 3 % to build wall time, on the host and on the judge's 4 CPUs;
- full size on the host: from 1841 s to at most 1000 s;
- tmpfs use for crash safety at most 1× the .blend size.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the bench scene's geometry hashes equal those of the base commit at the same Blender thread count;
- killing Blender (`kill -9` or `taskkill /F`) during three different slow commands, then recovering, gives the same scene measures as an uninterrupted run;
- a failed command is not replayed;
- a changed input file is reported on recovery;
- the overhead stays under the target on the check-size bench;
- the snapshot swap is atomic, so a crash during a snapshot leaves the previous snapshot and journal usable.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes:
  - no turning safety off;
  - no skipping recovery for some commands without a stated reason;
  - identical scene output.
- **Allowed files:**
  - `bridge/blendworks_bridge/autosave.py`, `handler.py`, `blendfile.py`, `limits.py` and its parts, a new journal module;
  - `bridge/session.py`, the transport and idle detection;
  - `bench/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most one Blender process of your own at a time during development, and two for the full check.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the benchmark at base and with the patch:
   - the targets hold;
   - the geometry hashes match at the same thread count;
   - a forced crash mid-build recovers to the same scene.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
