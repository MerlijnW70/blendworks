# Job: Riparian ground — a waterside as full and lived-in as a real one

Close to the camera at a river or lake, Blendworks ground reads empty and "very 3D made":
- sparse tufts on bare soil;
- stones that sit on top of the ground, with a clean cut and a bare ring of cover around them;
- no sediment, no litter, no zonation.

In a test the meadow preset thins near water to scattered tall reeds even with a three times larger budget. The owner's reference for the density and richness to reach is the job workspace, a dry hill meadow from an earlier render. The waterside should be as full as that, with waterside plants instead.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Riparian zonation.**
   - Plant communities by distance to the water line and wetness, from cited riparian ecology:
     - emergent reeds and rushes in the shallows;
     - sedges and rushes at the water's edge;
     - tall wet grasses and herbs;
     - then meadow;
     - mosses on damp shaded ground and on stones near the water.
   - Cover near the camera is dense: the bare ground fraction visible within 10 m of the camera stays under a stated share, measured against the reference image.
   - Uses `leaf_optics` for all new plants.
2. **Sediment.**
   - Gravel, sand, silt and mud on banks and beds, by flow energy: Hjulström/Shields-style sorting from the river's velocity, finer in slack water and on inner bends, coarser where the flow is fast.
   - Small gravel and pebble scatter near the camera.
   - Wet, dark, glossy mud at the water line, with the weather's wetness.
3. **Drift line.** A band of litter at the high-water mark: dead leaves, twigs, reed fragments, small sticks. The height comes from the water level plus a stated range, and the density from cited ranges.
4. **Stones in the ground, not on it.**
   - Burial depth from cited distributions, so some stones show only their top.
   - The ground deforms around each stone: a soil collar on land; in water, a scour hollow on the upstream side and sand behind.
   - A soil and moss stain line on the stone at the contact.
   - Cover grows right up to and against stones, with no clearance ring. Blades lean on them.
   - This applies to `shore_stones` and to scattered rocks.
5. **Dry meadow does not regress.** The dry-meadow density the owner liked stays: a test pins it.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the zonation order with distance to water;
- bare ground fraction near the camera under its limit at a riverside;
- sediment grain size decreases with lower flow velocity;
- the drift line lies within its height band;
- no gap and no bare ring at the stone–ground contact, measured on the mesh and in a render;
- dry-meadow density unchanged within a tolerance.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes: cited ecology and sediment physics, no per-scene tuning.
- **Allowed files:**
  - ground-cover presets, populations and placement;
  - `shore_stones` and the scatter contact;
  - the meadow fields;
  - new riparian, sediment and litter modules;
  - `leaf_optics` for new leaf types;
  - `docs/examples/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- `bank-form` (terrain shape, near-ground displacement), `horizon-seam`, `cloud-bases` and `stable-tests` run in parallel. Read terrain shape from the mesh and don't edit the terrain-shaping or heightfield code.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the river close-up (`docs/examples/river_closeup.py`) and the lake shore, with `render_final` at default settings. Compared with CC0 photographs of small river banks, the waterside reads full, natural and lived-in, with stones embedded in the ground.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
