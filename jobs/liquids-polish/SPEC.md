# Job: Liquids polish — honey classes, natural shore stones, spills and the open review notes

The liquids job was accepted with notes. These items are visible in the renders or were found in review:
- Shore stones sit like a string of pearls of egg-shaped stones along the water line.
- The honey colour is fixed to one USDA class.
- A coffee spill is thick and uniform with a faint rim.
- `liquid_depth` goes stale when the ground is deformed without changing its vertex count (`liquid_world.py`).
- The last body's `shore_width` overwrites the wet bands of earlier bodies.
- `ground_cover` re-measures water slowly on big terrains.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Honey by class.** Honey takes a colour class from the USDA scale, water white through dark amber, with absorption values from a cited source for each class and a documented default.
2. **Natural shore stones.**
   - Stones along water are placed by natural rules: clustered, with irregular spacing, sizes from a stated distribution, partly buried and partly submerged.
   - They are shaped from the existing rock tools (`fracture`, `chip`, `abrade`) into angular-to-rounded forms by how far water moved them.
   - No string-of-pearls rows along the water line.
3. **Spills that read as spills.**
   - A spill's thickness follows a liquid's real spreading: its height is set by surface tension and contact angle (cited).
   - It has a thin, visible meniscus rim.
   - Its outline is irregular.
4. **Correct state.**
   - `liquid_depth` is recomputed when the ground changes in any way.
   - Each water body keeps its own wet band.
   - `ground_cover` re-measures water at a cost that stays bounded on big terrains.
5. **Docs.** Command reference updates.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- honey colour per class within a stated tolerance of the cited values;
- the spacing statistics of shore stones are clustered (a stated nearest-neighbour index below 1) and not regular;
- the stones' shape varies (stated range of a roundness measure);
- the spill's height matches the capillary estimate within a tolerance, and its rim is present;
- deformed ground updates `liquid_depth`;
- two bodies keep two wet bands;
- the ground-cover re-measure time stays under a stated bound on a large terrain.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- No quick fixes: fix in general code and use cited values.
- **Allowed files:**
  - the liquid modules and commands;
  - `material_liquid`;
  - the scatter and ground-cover shore placement code;
  - the rock tools where shore stones need them;
  - `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own.

## Acceptance

1. `npm run check` passes on Windows and inside the judge image with the patch applied to `main` at the commit the delivery names.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders, with `render_final`:
   - the lake example close to its shore;
   - honey in all classes;
   - a coffee spill on a table.

   Each looks natural.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
