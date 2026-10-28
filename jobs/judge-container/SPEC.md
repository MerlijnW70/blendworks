# Job: Judge untrusted work inside Solive's Docker sandbox

Blendworks jobs are judged through Solive's `intent-engine judge`, which signs the verdict with the attestor key. So far the kit ran it with `--sandbox none`: the judge command, Blender's C importers (.blend, FBX, OBJ, Draco, image decoders) and, for code jobs, the worker's own patch under `npm run check`, all ran on the machine that holds the wallet keys. Blendworks' own Blender sandbox is strong in WSL (namespaces) but on Windows only limits writes ("reads are not limited", "network not isolated" in `src/judge/sandbox.ts`). Solive already offers `--sandbox docker` with a pinned image (`--sandbox-image <name>@sha256:<hex>`), memory and CPU caps, which keeps the key outside the evaluation. Build what Blendworks needs to use it, and close the audit's remaining isolation gaps as a second layer.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Judge image:** a reproducible Docker image (Linux) with Blender 5.2.3 (sha256-verified download), Node, and Blendworks at a given commit with its dependencies installed from the lockfile; `npm run judge:image -- --commit <sha>` builds it and prints the image digest; the image runs as a non-root user with no network at run time, a read-only root filesystem and a writable work folder only. CPU rendering by default (document how a GPU could be passed through later, without enabling it).
2. **Two entry points inside the image,** usable as Solive's `--run` command: `asset` (judge a delivered asset against an asset spec with `blendworks judge`, write the verdict) and `patch` (apply a delivered patch to the image's commit and run `npm run check`, write the verdict), each refusing work outside its input folder and writing a machine-readable result Solive can read.
3. **Kit integration (documented, scripts in `scripts/`):** commands that produce the exact `intent-engine judge --sandbox docker --sandbox-image <name>@sha256:… --sandbox-memory … --sandbox-cpus …` invocation for an asset job and for a code job, so the attestor key never enters the container.
4. **References refused before Blender starts** (defence in depth, all platforms): in TypeScript, before any Blender process starts, refuse a delivery whose OBJ/MTL, FBX (binary and ASCII), .blend (library and image paths) or glTF URIs are absolute, UNC, have a scheme, or escape the asset folder after normalisation; one shared path policy for delivery copy, validator and the Python side, with a table test of tricky paths (encoded, mixed separators, `..`, drive-relative, `\?\`, long paths).
5. **WSL/Linux mounts:** `bridge/judge/sandbox.sh` decodes mountinfo octal escapes and confirms every intended mount is read-only after remounting, failing closed; test with a path containing a space.
6. **Fail closed:** `--require-isolation`, on by default for `judge`, turns missing isolation (no container or namespaces, no memory cap, writable mounts, the Windows low-integrity-only mode) into an infrastructure error that is not a verdict; local previews opt out explicitly. The Windows low-integrity mode stays available only for local previews.
7. **GPU kernel cache:** after the warm run, the cache folder is not writable by low-integrity processes, kernels are hash-checked before each copy, and a mismatch rebuilds the cache.
8. **Docs:** `docs/DESIGN.md` states the threat model, the layers (Solive container, Blendworks sandbox, reference refusal), what each platform guarantees, and the exact way to judge paid work.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Container tests run where Docker is available and are skipped visibly otherwise; this machine has Docker Desktop (start it when needed). Include: no network from inside the container, no read outside the input folder, the image digest is stable for one commit, a hostile patch cannot read a file planted outside its folder, each refused reference kind.

## Rules

- Follow `CONTRIBUTING.md`. Never weaken an existing isolation test. Do not touch the user's wallet files, keys or Solive configuration; tests use throwaway keys only, and nothing goes on-chain.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `src/package/native-run.ts`, `scripts/**` (new judge-image and kit scripts), a `docker/` folder, `package.json` scripts, `test/judge/**`, `test/package/**`, `docs/**`.
- **Files shared with other open jobs:** dev-infra owns most of `scripts/lib/**` and `test/tooling/**`; add new files rather than editing theirs. If it lands first, rebase.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes run at once, 2 by default; do not raise it and do not run several full checks at once.
- **While working:** iterate with `npm run check:fast` and single test files. Run `npm run check` once, at the end, at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge builds the image, judges every proof asset in `artifacts/proof` inside it with unchanged verdicts, runs one past code delivery through the `patch` entry point with a pass, and confirms from inside the container that the network and the host's other folders are unreachable.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
