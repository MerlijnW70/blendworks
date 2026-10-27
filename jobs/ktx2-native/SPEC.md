# Job: Real KTX2 texture compression through the native gltfpack

`blendworks package` can't write KTX2 today. The npm gltfpack build has no BasisU, so the `package.ktx2` rule always fails honestly, and textured assets stay large: the armillary is 14.6 MB uncompressed and 9.7 MB after meshopt, almost all of it textures. Add the official native gltfpack, which includes BasisU, as a verified, pinned tool, so packages get real KTX2 textures.

## Base

- **Base commit:** `8f55cfd`. Rebase onto the latest `main` before delivering.

## Required

1. **A pinned native binary:**
   - `npm run tools:gltfpack` (and `doctor`) installs the official gltfpack release binary for the platform (Windows x64, Linux x64; macOS if available) from the zeux/meshoptimizer GitHub release.
   - The version and the sha256 of every platform archive are pinned in one file in the repo. A download whose hash does not match is refused and deleted. Nothing is ever run unverified.
   - The binary lives in the cache root and is never committed. `BLENDWORKS_GLTFPACK` can point to a binary installed by the user, and the version check still applies to it.
2. **Selection:**
   - The packager prefers the native binary when it is verified and supports BasisU, which it probes at run time as today. Otherwise it falls back to the npm build, as now.
   - The report states which gltfpack ran (native or npm), its version and its capabilities.
3. **Texture modes:**
   - ETC1S for colour maps and UASTC for normal and data maps, with documented quality settings and mipmaps.
   - Colour spaces stay correct (sRGB colour, linear data).
   - The GPU-memory estimate for KTX2 uses the compressed GPU formats, and DESIGN documents the formula.
4. **Validation and equivalence:**
   - Compressed outputs pass the Khronos validator, with 0 errors and the KHR_texture_basisu extension declared correctly.
   - Equivalence checks the texture slots, the counts and the dimensions, including mip levels, from the KTX2 headers parsed in the repo.
   - A KTX2 file whose header is corrupt fails.
5. **Sandbox:**
   - The native binary runs with the same limits as the judge's other tools: a timeout, a memory cap, and no network where the platform isolates it.
   - Arguments are built as arrays, never through a shell.

## Tests

- Hash pinning: a wrong hash is refused, and nothing is executed.
- Selection order and fallback, with a stubbed binary.
- Real KTX2 when the native binary is present, skipped otherwise:
  - a textured fixture produces valid KTX2 with mips;
  - normal maps are UASTC and colour maps ETC1S;
  - the validator reports 0 errors;
  - the equivalence holds.
- Header parsing of KTX2 fixtures generated in the test, including a corrupted one.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:** `src/package/**`, `scripts/` (the tools script and doctor), `package.json` (scripts), `test/package/**`, `docs/DESIGN.md` §7, and the README env table.
- **Files shared with other open jobs:** `bridge-extras` and `judge-extras` do not touch these.
- **Environment:**
  - Set `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe`.
  - Run at most `BLENDWORKS_JOBS` Blender processes.
  - Network access is needed once, to download the release; verify it against the pinned hash.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when the hash check is bypassed, or when a normal map is encoded as ETC1S.
3. The judge installs the native binary and packages the armillary sphere with `ktx2: true`. The judge reviews the size and GPU-memory table and the LOD renders, which must look the same as with PNG textures.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
