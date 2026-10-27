# Job: A judge that cannot be gamed and gives the same verdict everywhere

The judge decides payments, so its verdict must be correct, repeatable and hard to game. An audit found real measurement bugs, ways to pass rules with a bad asset, a verdict that can depend on machine speed, and isolation gaps. Fix all of them properly. Verify each finding in the code first, and report any you find to be wrong.

## Required

1. **Measurement bugs:**
   - **Instanced meshes:** shared mesh data is measured once per mesh datablock for UV and topology, and once per instance for triangles and objects. Today four wheels sharing one mesh fail UV overlap (`judge_geometry.py`, the key is the object name).
   - **Animation:** measurement sets a fixed frame (frame 1, or a documented rest pose for armatures) before evaluating, the same frame the render uses. This applies to `measure.py` and `closeups.py`.
   - **Units:** a `.blend` delivery is measured in metres through `unit_settings.scale_length`.
   - **Axes:** the axis convention is stated in the schema and `docs/DESIGN.md`: Blender Z-up, with glTF Y-up mapped. An optional `upAxis` in the spec maps the axes for hirers who think in glTF axes.
   - **UV outside the unit square:** UVs outside 0–1 are reported (`uvOutsideUnitSquare`). Overlap and coverage use a documented rule, for UDIM tiles or wrapped.
2. **Rules that resist gaming:**
   - Bounds, size and origin use vertices that belong to faces. Loose vertices and wire edges are reported, and fail `manifold`.
   - Measure and report:
     - degenerate faces (by area epsilon);
     - duplicate faces (coincident vertex sets);
     - interior or hidden faces: an estimate of surface that is never visible from outside, computed with a BVH ray test from a fixed, seeded set of directions;
     - inverted shells (negative signed volume);
     - the number of closed shells.
   - Add rules for them: `faces.maxDegenerate`, `faces.maxDuplicate`, `faces.maxHiddenRatio`, `shells.max`, `manifold.noInverted`, and `triangles.minVisible`, which counts only faces visible from outside.
   - UV coverage is weighted by 3D surface area, and faces with zero 3D area are ignored.
   - Each rule is documented in `docs/DESIGN.md` section 3, with what it prevents.
3. **The verdict depends on measurement only:**
   - The measure and validation stages decide pass or fail. The render stage is evidence.
   - If rendering fails or times out, the report says so and the verdict stands. A new optional rule, `renders.required`, can make renders mandatory.
   - Render cost is bounded by a triangle and pixel budget, not only by wall-clock time.
   - Two judges on machines of different speed give the same verdict for the same asset and spec. Test this by simulating a slow render.
4. **Judge a private copy:**
   - The judge copies the delivery (the main file, plus referenced files for `.gltf`, `.obj` and `.fbx`) into a private temp folder and judges only that.
   - It hashes the whole delivered file set, and the report records that hash.
   - `fileSize` counts every file in the set.
   - Unresolved external references in OBJ or FBX are reported and fail the delivery when the spec requires self-contained files.
5. **Importer limits before evaluation:**
   - glTF deliveries are pre-checked from their JSON before import: accessor counts against the triangle cap, image dimensions from headers, and Draco or meshopt extensions according to a documented policy.
   - Modifiers that multiply geometry (array, mirror, geometry nodes, screw, subdivision) are estimated or refused before the depsgraph is evaluated, so huge inputs fail with a clear `too_many_triangles` and not a crash.
6. **Stronger isolation:**
   - In WSL or Linux, run the judge's Blender with a read-only view of the filesystem, plus a private writable work folder and `/tmp`. Use a mount namespace (`unshare -m` with read-only binds) or `bwrap` when it is available, plus a PID namespace and the existing network namespace and memory limit.
   - Report the isolation in the summary, and fall back clearly when a mechanism is missing.
   - On Windows, document what is and is not isolated. Add whatever is reliably available without admin rights, for example an AppContainer or a restricted token, after you have verified that it works.
   - Tests prove that a judged asset cannot read a file outside its folder in WSL.
7. **Per-object rules:** add `objects[]` rules matched by name glob: `required`, `triangles`, `size`, `origin` or pivot per object, and `materials`. Also add `size.maxExtent` and `size.minExtent`, and an `origin` given as a point with a tolerance.
8. **Diff tool:** `blendworks diff <reportA> <reportB>` compares rules, measurements and per-view image hashes, for revision rounds and disputes.

## Tests (fixtures generated in headless Blender)

- **Instancing:** four instances of one mesh pass UV overlap. Triangles count all four.
- **Animation:** an animated asset gives the same bounds whatever frame it was saved on.
- **Gaming:**
  - padding with hidden interior triangles fails `triangles.minVisible` and `faces.maxHiddenRatio`;
  - degenerate and duplicate faces are caught;
  - an inside-out shell fails `manifold.noInverted`;
  - extra tiny shells fail `shells.max`;
  - a loose vertex no longer changes size or origin.
- **Verdict:** a forced render timeout leaves the verdict unchanged, and `renders.required` makes it fail.
- **Private copy:** changing the original file after the copy has no effect. `fileSize` includes OBJ and MTL siblings.
- **glTF pre-check:** a glTF claiming 50 million triangles is refused before import.
- **Isolation (WSL):** a reading probe outside the asset folder fails.
- **Old specs:** existing specs give the same verdicts as before on the existing fixtures, except where a bug fix changes them. List those changes.

## Rules

- Follow `CONTRIBUTING.md` and `jobs/TEMPLATE.md` if it exists.
- Touch only `src/judge/`, `bridge/judge/`, `schemas/`, `test/judge*`, and sections 3–5 of `docs/DESIGN.md`. You may update existing tests that assert behaviour this spec changes; list them.
- Other open jobs (session-robustness, modeling-kit, dev-speed) do not touch the judge, except dev-speed's test setup helpers. Rebase onto the latest `main` before delivering.
- Keep the PC usable: one Blender process at a time, and run the full check at low priority.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names.
2. A test fails for each gaming fixture when its rule is removed, and when the verdict starts depending on render success.
3. The judge re-judges the five proof assets (`artifacts/proof/*.glb`) with their original specs and gets the same verdicts, except where a bug fix explains a change. The judge also re-judges one gaming fixture, which now fails.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
