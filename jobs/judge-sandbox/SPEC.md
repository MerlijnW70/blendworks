# Job: A judge sandbox that holds against hostile assets on every platform

The judge decides payment for assets from unknown workers, so the delivered file is hostile input to Blender's C importers (.blend, FBX, OBJ, Draco, image decoders). A security audit found the isolation too weak where it matters most:
- On Windows the low-integrity token limits writes only: reads are not limited and the network is not isolated (`src/judge/sandbox.ts`, `windowsPlan`). A parser exploit could read wallet keys on the same machine and send them out.
- External references in OBJ/MTL, FBX and .blend files (absolute paths, UNC/SMB, `..`) are opened by Blender before `refuse_external_files` runs (`bridge/judge/judge_load.py`), which can leak NTLM hashes over SMB and read data outside the hashed delivery.
- The GPU kernel cache keeps the low-integrity label after the warm run, so a compromised run could poison kernels used by later runs (`src/judge/gpu-cache.ts`, `kernel-cache.ts`).
- `bridge/judge/sandbox.sh` matches mount points from mountinfo without decoding `\040`, so `remount,ro` silently fails on paths with spaces.
- Missing isolation fails open: the verdict still counts when the launcher or namespaces are unavailable, and native gltfpack on Windows runs without a memory cap.
Close each at its root.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Windows isolation:** run sandboxed Blender (and native tools such as gltfpack) in an AppContainer or LPAC token with no network capability, no access to the user profile or other drives, read access only to the Blender installation, the judge scripts and the private delivery copy, and write access only to the private work folder. Prove both limits with tests: a script inside the sandbox cannot read a file in the user profile or on another folder of the same drive, and cannot open a TCP connection. If an AppContainer cannot be created on a machine, the run reports the isolation as missing (item 5).
2. **References refused before Blender starts:** in TypeScript, before any Blender process starts, scan OBJ/MTL, FBX (binary and ASCII) and .blend files (library and image paths in the file's blocks) and glTF URIs, and refuse the delivery when any reference is absolute, UNC, has a scheme, or escapes the asset folder after normalisation. Keep one URI/path policy shared by delivery copy, validator and the Python side, with a test that the three agree on a table of tricky paths (encoded, mixed separators, `..`, drive-relative, `\\?\`, long paths).
3. **Kernel cache:** after the warm run, reset the cache folder's integrity label (or ACL) so low-integrity processes cannot write it, record hashes of the kernels, and verify them before each copy into a run; a mismatch rebuilds the cache and is reported.
4. **Linux/WSL mounts:** decode mountinfo octal escapes, and after remounting confirm with `findmnt` (or by re-reading mountinfo) that every intended mount is read-only; fail closed otherwise. Test with a path containing a space.
5. **Fail closed for paid judging:** a `--require-isolation` flag, on by default for `judge` (off explicitly for local previews), turns any missing isolation (no AppContainer, no namespaces, no memory cap, writable mounts) into an infrastructure error that is not a verdict; the report states exactly what was missing.
6. **Docs:** `docs/DESIGN.md` (sandbox and isolation sections) states the threat model, what each platform guarantees, and how to judge safely; remove "reads are not limited" once it no longer holds.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Platform-specific tests run on the platform they cover and are skipped visibly elsewhere; this machine runs both Windows and WSL, so run both.

## Rules

- Follow `CONTRIBUTING.md`. Never weaken an existing isolation test.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `src/package/native-run.ts` and its tests, `test/judge/**`, `test/package/**`, `docs/**`.
- **Files shared with other open jobs:** other judge jobs may be queued after this one; none run at the same time.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge runs the isolation tests on Windows and in WSL, and judges all proof assets in `artifacts/proof` with `--require-isolation` on both platforms with unchanged verdicts.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
