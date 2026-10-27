# Job: Judge rules for rigs, animation, vertex colours, and comparison with a reference

The judge measures static geometry, textures and visual fit. A market for game assets also needs:
- rules for characters and props that move: armatures, skinning and animation clips;
- rules for vertex colours;
- an objective comparison against a reference the hirer provides, either a silhouette or an image of the intended shape.

Add these as measured, deterministic, documented rules.

## Base

- **Base commit:** `8f55cfd`. Rebase onto the latest `main` before delivering.

## Required

1. **Rig and skin measurement:**
   - Measure the armature: bone count, hierarchy depth, root bone, and the bone names matched against an optional naming scheme (for example a standard humanoid bone map given in the spec).
   - Measure skinned meshes: the maximum influences per vertex, the number of unweighted vertices, the number of vertices whose weights do not sum to 1 within a tolerance, and whether the skin is bound in rest pose.
   - New rules: `rig.required`, `rig.maxBones`, `rig.requiredBones`, `skin.maxInfluences` (game engines typically need 4 or fewer), `skin.maxUnweighted` and `skin.normalized`.
2. **Animation measurement:**
   - Measure clips (glTF animations or Blender actions): name, duration, frame rate and keyframe counts.
   - Check that each clip loops: the first and last poses match within a tolerance, when the spec asks for it.
   - Check that the root motion stays within bounds.
   - Evaluate the clips at sampled frames and record the bounds over the whole clip, so assets cannot clip outside their stated size while animating.
   - New rules: `animation.requiredClips` (names), `animation.loop`, `animation.maxDuration` and `animation.boundsWithin` (the size rule over every sampled frame).
3. **Vertex colours:**
   - Measure the colour attributes: count, domain (point or corner), data type, and whether they are present on every mesh.
   - New rules: `vertexColors.required` and `vertexColors.domain`.
4. **Reference comparison:**
   - The spec may include `reference: { views: { front: { sha256, mask } } }`. The hirer delivers reference silhouette masks (PNG) or images, pinned by sha256, beside the spec.
   - The judge renders the asset's silhouette in the same fixed views with the same rig. It computes silhouette IoU (intersection over union) and a boundary distance (the mean distance between the two silhouette edges in pixels, as a fraction of the view size), with the math documented.
   - Rule: `reference.minIoU` and `reference.maxBoundaryDistance` per view or overall.
   - The reference files are untrusted input: check their size, dimensions and format. They are never executed or sent anywhere.
5. **Fixtures and docs:**
   - Generate in headless Blender a rigged, skinned, animated character-like fixture: a simple jointed figure with a looping walk clip. Generate variants with errors: 5 influences per vertex, unweighted vertices, a clip that does not loop, and a clip that moves out of bounds.
   - Add a vertex-colour fixture, and reference masks made from known shapes.
   - Document every rule in DESIGN §3 with what it prevents.

## Tests

- Every rule passes on the good fixture and fails on its broken variant, with expected values worked out by hand: bone counts, influence counts, the loop tolerance and the IoU of known shapes, for example a square against a circle.
- Old specs give the same reports as before.
- Reference inputs that are malformed or oversized are refused cleanly.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md`.
- **Allowed files:** `src/judge/**`, `bridge/judge/**`, `schemas/`, `test/judge*`, and `docs/DESIGN.md` §3–5.
- **Files shared with other open jobs:** none. `ktx2-native` touches `src/package`, and `bridge-extras` touches the bridge.
- **Environment:** set `BLENDER=F:/tools/blender-5.2.3-windows-x64/blender.exe`, and run at most `BLENDWORKS_JOBS` Blender processes.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails for each broken fixture when its rule is removed. Prove this by breaking the code once.
3. The judge judges the rigged fixture and one broken variant, and a reference comparison of a proof asset against a mask made from its own front view, which must score an IoU of 1, and against a wrong mask.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
