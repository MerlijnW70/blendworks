# Job: Game-ready packages — automatic LODs and compression

A judged asset is one `.glb` at full detail with uncompressed textures. Games need levels of detail and compressed geometry and textures. Add a packaging step that turns a passing asset into a game-ready package: LODs with controlled visual error, meshopt-compressed and quantised geometry, and KTX2 (Basis Universal) textures. Every output is validated and checked against the source, so that compression cannot silently break the asset.

## Base

- **Base commit:** `23ed46a`. Rebase onto the latest `main` before delivering.

## Required

1. **LOD generation:**
   - The bridge command `generate_lods` and the CLI `blendworks package` build LOD1..LODn from LOD0.
   - Each LOD comes from a target triangle ratio, or from a target screen-space error at a stated distance.
   - Use Blender decimation that preserves UV seams, borders and material boundaries, and keep the normals right (weighted normals after decimation).
   - Name LODs by the documented convention (`<name>_LOD<n>`), and export them in one `.glb` or one file per LOD, as configured.
   - For each LOD, report the triangle count, the ratio and the measured geometric error (Hausdorff distance to LOD0 through BVH sampling, in metres and as a fraction of the bounds).
2. **Visual check of LODs:**
   - Render each LOD and LOD0 from the judge's fixed views at the distance where that LOD would switch in.
   - Report silhouette IoU and an image similarity score, implemented in the repo with documented math.
   - A LOD that falls below the configured thresholds is reported, and fails when the rule is set.
3. **Compression:**
   - Use `gltfpack` (the official npm WebAssembly build, pinned exactly; add it to the allowed runtime dependencies) for meshopt compression and quantisation, and KTX2/Basis textures where the build supports it.
   - Verify texture support at runtime and document the fallback if the npm build cannot write KTX2. Do not fake it.
   - Keep colour and data textures in the right modes: UASTC for normal maps, ETC1S or UASTC for colour by a documented rule.
   - Produce both an uncompressed and a compressed package, and report the sizes and estimated GPU memory before and after.
4. **Validation and equivalence:**
   - Run the Khronos validator (already a dependency) on every output, with 0 errors required.
   - The judge's Blender importer cannot read meshopt or KTX2. So judge the uncompressed package with Blender, and check the compressed one against it with the validator, plus decoded equivalence: triangle count, bounds within the quantisation tolerance, the same materials and texture slots, and the same node hierarchy.
   - Use `gltfpack` or `gltf-validator` data for these checks, not Blender.
5. **Spec rules** (schema, `src/judge/spec.ts`, `docs/DESIGN.md` §3):
   - `lods: { count, ratios | maxScreenError, minSilhouetteIoU }`;
   - `package: { compressedMaxBytes, ktx2: true|false, meshopt: true|false }`.
   The judge runs packaging when these rules are present and judges the results. Specs without them behave exactly as before.
6. **For agents:** add MCP-level access through the bridge `generate_lods` command, plus a `package` step documented in the MCP instructions, so an agent can check its LODs before delivering.

## Tests (values worked out by hand where possible)

- **Ratios:** a subdivided sphere decimated to 50% and 25% gives triangle counts within tolerance, with the Hausdorff error below a value derived from the sphere.
- **UV seams:** a UV-seamed cube keeps its seams, and the UV overlap does not grow.
- **Silhouette check:** a LOD with a deliberately broken silhouette fails `minSilhouetteIoU`.
- **Compression round trip:** a textured asset gives a meshopt + KTX2 package with 0 validator errors, equivalent counts, bounds and materials, and a smaller file size.
- **Old specs:** they are unchanged.
- **Proof assets:** the drill rig (142k triangles) packages into 3 LODs. Report the numbers.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:**
  - `src/package/**` (new) and `bridge/package/**` (new);
  - `bridge/blendworks_bridge/commands/` (a new `lods.py`) and `__init__.py`;
  - `src/judge/` (the spec, rules and run wiring for the new rules only);
  - `schemas/`, `test/`, `bridge/tests/`;
  - `scripts/rules.mjs` and `CONTRIBUTING.md` (the dependency lines only);
  - `package.json`, `package-lock.json`;
  - `docs/DESIGN.md` §3 and a new packaging section;
  - `README.md` (one usage line).
- **Files shared with other open jobs:** `visual-judge` edits `src/judge/spec.ts`, `src/judge/run.ts`, `schemas/` and `docs/DESIGN.md` §3. The job that lands second rebases.
- **Environment:** `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe`, with at most `BLENDWORKS_JOBS` Blender processes. Iterate with `check:fast`, and run `check` once at the end at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when the silhouette check is skipped, when validation of compressed output is skipped, or when the equivalence check stops comparing bounds.
3. The judge packages the drill rig and the armillary sphere, inspects the LOD renders side by side, and reviews the size and GPU-memory table.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
