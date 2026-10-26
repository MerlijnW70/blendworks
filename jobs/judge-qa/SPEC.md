# Job: Texture rules, glTF validation and loose-part rules in the judge

The judge measures geometry well but checks nothing about textures, which realistic assets depend on, and it does not run the official glTF validator. Add texture rules to the asset spec, run the Khronos glTF-Validator on every glTF delivery, and add a rule for floating parts.

## Required

1. **Spec schema** (`schemas/asset-spec.schema.json` and `src/judge/spec.ts`): add optional rules, documented in `docs/DESIGN.md` section 3 with an example.
   - **`textures.required`:** the map kinds every material must have, from `baseColor`, `metallicRoughness`, `normal`, `emissive` and `occlusion`.
   - **`textures.minSize` / `textures.maxSize`:** limits in pixels on the shorter and longer side.
   - **`textures.embedded`:** every image is inside the file, with no external URIs.
   - **`textures.maxCount`:** the maximum number of distinct images.
   - **`textures.maxGpuBytes`:** an estimated GPU memory budget, uncompressed RGBA8 with a full mip chain. The formula is documented in `docs/DESIGN.md`, and compressed formats are counted by their decoded size.
   - **`textures.powerOfTwo`:** whether texture sizes must be powers of two.
   - **`gltf.validator`:** the maximum number of errors and warnings, with errors 0 by default when the rule is present.
   - **`parts.maxFloating`:** the number of loose parts that touch no other part, measured with a stated tolerance in metres.
2. **Texture measurement** (`bridge/judge/`): read every material's texture slots from the imported glTF.
   - Report the map kind, image size, colour space, embedded or external state, and which materials use each image.
   - The colour space must be right for each kind: sRGB for base colour and emission, non-colour for data maps. A mismatch is reported as its own measurement.
3. **glTF validation:** run the Khronos glTF-Validator (`gltf-validator`, the official npm package, Apache-2.0) on `.glb` and `.gltf` deliveries.
   - It runs in the Node process with a size cap, and never opens external URIs.
   - The report lists every issue (code, severity, pointer, message), and the rule compares the counts.
   - Add `gltf-validator` to the allowed runtime dependencies in `scripts/rules.mjs` and `CONTRIBUTING.md`, pinned to an exact version.
4. **Floating parts:** a loose part counts as floating when its bounds, grown by the tolerance, overlap no other part and no other object. Report the floating parts by object and an index, with their bounds.
5. **Report and summary:** every new rule appears in `report.json` and in the text summary with its measured value and limit, like the existing rules. The contact sheet header shows the texture count and the estimated GPU memory.
6. **Determinism:** the measurements are exact and repeatable, following `docs/DESIGN.md` section 5.

## Tests (fixture assets generated in headless Blender, not committed binaries)

1. **Textured asset:**
   - A fully textured asset with embedded PBR maps passes every texture rule.
   - The same asset with a missing normal map fails `textures.required`.
   - With a wrong colour space on a data map, the mismatch is reported.
   - With an external image, it fails `textures.embedded`.
   - A non-power-of-two image fails when `powerOfTwo` is set.
2. **GPU budget:** the GPU-memory estimate for a known set of images matches a value worked out by hand in the test.
3. **glTF validation:** a `.glb` corrupted on purpose (for example a broken accessor) produces validator errors and fails the rule. A clean export reports 0 errors.
4. **Floating parts:** a scene with one part hanging in the air fails `parts.maxFloating: 0`. The same parts touching pass.
5. **Old specs:** existing specs without the new rules give exactly the same report as before.

## Rules

- Follow `CONTRIBUTING.md`.
- Touch only `src/judge/`, `bridge/judge/`, `schemas/`, `test/judge*`, `scripts/rules.mjs` (the dependency allowlist only), `CONTRIBUTING.md` (the dependency line only), `package.json`, `package-lock.json`, and sections 3 and 4 of `docs/DESIGN.md`.
- The speed job (`jobs/speed`) changes the same judge files. Start from `main` after it has landed (the judge will say when), and rebase onto the latest `main` before delivering.
- No quick fixes: each rule is complete, validated and tested as specified.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails when the validator is skipped, when colour-space mismatches stop being reported, or when the GPU estimate changes.
3. The judge runs the extended judge on the pickaxe asset (`jobs/asset-pickaxe`, delivered at `artifacts/proof/pickaxe.glb` on the judge's machine) with a spec that adds texture rules, and gets correct texture measurements and 0 validator errors.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
