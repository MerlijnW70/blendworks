# Job: An MCP server that survives a bad Blender day, and a library that tolerates one bad file

An audit of the MCP server and library client found failures an agent cannot recover from:
- One failed `open()` during a restart marks the session dead for good (`src/mcp/connection.ts`), so a slow cold start or a briefly locked `blender.exe` ends the session until the MCP server is restarted.
- The server starts Blender before answering `initialize` (`src/mcp/index.ts`, `src/mcp/start.ts`), so a cold start can exceed the client's connect timeout and a missing Blender shows only "server failed".
- A garbled reply line is dropped silently (`src/mcp/line-link.ts`), so the call waits its full timeout (up to 660 s) before recovery; the session and protocol layers define two reply types.
- `startSession` resolves on spawn, before the bridge is ready, and early exits repeat on every call with no backoff; the desktop probe silently loses a busy desktop Blender to a fresh empty headless one; there is no `unhandledRejection` handler, so a crash can orphan Blender; library tools ignore cancellation.
- Error texts lack the next step: a timeout does not mention `timeout_seconds` and its maximum; a dead session does not mention `BLENDER`; `bad_args` echoes the whole schema uncapped.
- The library validates the whole `/files` listing strictly, so one 8k file with a bad md5 refuses the asset even when 1k is requested, and `library_search` fails an entire page when one result's listing is bad (`src/mcp/library/schemas.ts`, `client.ts`, `index.ts`).
Fix each at its root.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Restart with backoff:** retry opening a session a few times with backoff before declaring it dead; a dead state ends only after a bounded number of failures in a time window, and a later call can try again; the message names the cause and the fix (check `BLENDER`, restart the server).
2. **Answer first, start Blender after:** connect the MCP transport before starting Blender; start the session in the background; calls made before it is ready wait for it within their own timeout, and a start failure becomes a tool error with the cause and a hint.
3. **Ready handshake:** a session is ready only after the bridge answers a cheap request; early exits back off; a garbled line for a pending id rejects that call at once with a `protocol` error and triggers recovery; one shared reply parser for session and line link; dropped lines are logged.
4. **Desktop mode:** log which mode was chosen and why; retry the probe once with a longer timeout when the port is open but slow.
5. **Process hygiene:** handle `unhandledRejection` and process exit so Blender children are never orphaned; library tools honour the cancellation signal.
6. **Actionable errors:** timeout messages state `timeout_seconds` and its maximum for that command; `bad_args` lists the failing fields first and caps the schema echo.
7. **Tolerant library:** parse listings loosely and validate md5 and size only for the files actually chosen, naming the file and suggesting another resolution when one is bad; `library_search` uses settled results and lists unavailable assets with a reason instead of failing the page; downloads stay strictly verified. Remove the note about refused assets in `docs/research/natural-shapes.md` once fixed.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Use the existing fake bridge and fake library server; add cases for a failing first restart, a slow start past a client's connect window, a garbled reply for a pending id, an early-exiting Blender, a listing with one bad 8k md5, and a search page with one bad asset.

## Rules

- Follow `CONTRIBUTING.md`.
- **Allowed files:** `src/mcp/**` except `src/mcp/instructions.ts` and `src/mcp/routing/**`, `src/session.ts`, `src/blender.ts`, `test/**` for the MCP, session and library tests, `docs/**`.
- **Files shared with other open jobs:** tree-mesh and tree-shape touch `src/mcp/instructions.ts` and routing files only; if they land first, rebase.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge starts the MCP server with a deliberately slow and then a missing Blender and sees `initialize` answered and actionable tool errors, and searches and downloads `boulder_01` at 1k.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
