# Job: Ground cover: grass, tufts, flowers and litter that make terrain read as real

A showcase scene built with Blendworks (trees, scattered rocks, scanned textures, an HDRI sky) still reads as CG mainly because the ground is a textured plane: real meadows and forest floors are made of thousands of grass blades, tufts, small flowers, twigs and leaf litter at many scales. Blendworks can scatter instances with Poisson spacing and masks, but has no ground-cover elements and no way to place millions of small ones efficiently. Build ground cover that holds up at eye level and stays renderable and exportable.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Element generators** (procedural, seeded, sized in metres, with UVs and materials from the leaf/grass presets): grass blade clumps (blade count, height range, curvature, width taper, colour variation from root to tip, dry-tip share), tufts and sedges, small flowers (built on phyllotaxis where it fits), twigs, fallen leaves and pebbles; each available as cards (alpha) and as real geometry, with a triangle budget per element.
2. **`ground_cover` command:** covers a target surface with layered populations (for example short grass everywhere, tall grass and flowers in clumps, litter under trees), each with density in elements per m², masks (slope, height, attribute such as erosion or deposition, distance to objects such as tree trunks and rocks, noise for patchiness), scale and colour variation, and a camera-aware density falloff (full near a given camera or point, sparser far away) so a 100 m field stays within a stated instance budget; instances, not realized geometry, by default.
3. **Contact and blending:** elements sit on the surface with their base embedded, tilt with the slope, and the ground material darkens where cover is dense (an attribute the material can use), so cover and ground read as one surface.
4. **Wind and export:** an optional wind attribute for game engines (vertex colours per element, documented), and glTF export with instancing (EXT_mesh_gpu_instancing where available) or realized LODs.
5. **Docs and MCP:** command reference, presets for meadow, forest floor, dry steppe and lawn, a workflow, the family line through the instructions mechanism on `main`.

## Tests

One negative test per acceptance item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include: density per m² within a stated tolerance per population; masks exclude what they claim (no grass on rock faces above a slope, none inside a trunk radius); the instance budget holds for a 100 m field; seeds repeat; elements sit on the surface (no floating base); export round-trips the instances. No wall-clock bounds; container-friendly render sizes.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief (the check must pass in the Linux judge image).
- **Allowed files:** new bridge modules and commands, `instancing.py` and the scatter modules where reuse needs it, material presets for grass and litter, `src/mcp/routing/**` data, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. At most `BLENDWORKS_JOBS` Blender processes at once, 2 by default.

## Acceptance

1. `npm run check` passes with the patch applied to `main` at the commit the delivery names, on Windows and in the judge image.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders an eye-level close-up and a wide shot of a meadow with trees and rocks dressed with ground cover, compares them with the same scene without it, and judges whether the ground now reads as real.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
