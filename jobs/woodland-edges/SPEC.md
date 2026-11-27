# Job: Woodland edges — trees in groups, with shrubs and understorey

Trees in Blendworks scenes stand alone, evenly spread like props. That gives no sense of scale, and the land reads as a game world. Real trees grow in stands, copses, hedgerows and forest edges, with shrubs, young trees and saplings at the margins. They sit in natural spacing patterns and age structures, and they shade and shelter the ground under them.

Add vegetation structure at the scale of groups and stands.

## Base

- **Base commit:** the `main` commit this spec is added in. Rebase onto the latest `main` before delivering.

## Required

1. **Stand patterns.**
   - A command places trees as copses, groves, hedgerows along given lines or field edges, and forest patches with edges.
   - Spacing follows cited spacing statistics: clustered at the stand scale and regular within a stand by competition.
   - Sizes and ages follow a stated size distribution: mature trees, younger trees and saplings.
   - Species mix by moisture and light.
2. **Shrubs and understorey.**
   - A shrub layer is grown with the existing tree tools as multi-stem shrubs, using new shrub presets: for example hazel, hawthorn, elder and willow scrub.
   - It fills forest edges and copse margins as a mantle.
   - Ferns and tall herbs grow under the canopy.
   - Shrubs and understorey thin out towards the open ground.
3. **Edges that read as edges.** A forest edge has a graded profile: from open ground through tall herbs and shrubs to saplings and the canopy. It must not stop at a straight line of trunks.
4. **Ground under trees.** The ground under the canopy changes: shade, leaf litter, sparser grass and moss. The ground-cover populations read the canopy.
5. **Budget and speed.**
   - Use instancing for repeated plants and `grow_trees` parallel builds for unique trees.
   - Stated triangle and memory budgets hold within the 8 GB judge.
6. **Working with what exists.** This builds on `grow_tree`, `grow_trees`, `tree_mesh`, `tree_leaves`, `scatter`, `ground_cover` and `distant_forest`. Near stands continue seamlessly into the distant forest cards.

## Tests

One negative test per required item: a test that fails when the behaviour the item names stops holding. Say how you proved it, for example by breaking the code once and watching the test fail. Include:
- the measured stand clustering at large scale and regularity at small scale;
- the size distribution;
- the edge profile (density of shrubs against distance from the canopy);
- grass under the canopy is sparser than in the open;
- the budgets hold;
- the same seed repeats.

## Rules

- Follow `CONTRIBUTING.md` and the worker brief.
- Blendworks builds everything itself.
- No quick fixes: no hand-placed plants; everything comes from general rules.
- **Allowed files:**
  - the tree presets and tree placement code;
  - new modules and commands for stands, shrubs and understorey;
  - `tree_batch` and `workers` where stands use them;
  - the canopy and shade inputs of ground cover (read-only interfaces; `meadow-structure` owns the ground-cover internals);
  - `docs/examples/**`, `bench/tool-selection/**`, `test/**`, `bridge/tests/**`, `docs/**`.
- **Environment and concurrency:** Blender 5.2 through `BLENDER`. The machine is shared: at most 2 Blender processes of your own, except for `grow_trees` measurements that you announce.

## Acceptance

1. `npm run check` passes on Windows with the patch applied to `main`.
2. Every required item has a test that fails when its behaviour stops holding.
3. The judge renders the lake example with woodland stands and a forest edge, plus a close view of a forest edge, at default `render_final` settings. Compared with CC0 photographs of a woodland edge and copses in open country, the trees read as real stands with shrubs and understorey.

## Deliver

One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.
