# Job: <what gets better, in one line>

<Two or three sentences: the problem today and the outcome wanted.>

## Base

- **Base commit:** <the `main` commit this spec was written against>. Rebase onto the latest `main` before delivering.

## Required

1. **<Part one>:**
   - <A testable statement of what must hold.>
2. **<Part two>:**
   - <...>

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it (for example, by breaking the code once and watching the test fail).

- <Test for required item 1, with values worked out by hand.>
- Fixture assets are generated in headless Blender by a fixture script (`test/judge/<name>_fixtures.py`), never committed as binaries.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** touch only <list every path or folder>. Existing tests that assert changed behaviour may be updated; list them in the delivery.
- **Files shared with other open jobs:** <job and file, or "none">. The job that lands second rebases and resolves the conflict.
- **Environment and concurrency:** Blender 5.2 through `BLENDER` (see `npm run doctor`). At most `BLENDWORKS_JOBS` Blender processes run at once, which is 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. <One item per behaviour, each checked by a test that fails when it stops holding.>
3. <What the judge runs by hand.>

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
