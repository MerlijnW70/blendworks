# Examples

## Engraved rings

`engraved_rings.py` builds an engraved brass ring pair on a marble plinth with Blendworks commands only, and renders close-ups. It is the acceptance build of the `modeling-3` job.

```
blender --background --factory-startup --python docs/examples/engraved_rings.py -- out
```

The script writes into `out`:
- `engraved-rings.blend`;
- six close-up PNGs (`BLENDWORKS_DEVICE` picks the render device, `auto` by default);
- `summary.json`: every command with its time, solver and mesh quality.

It runs these steps in order, and stops at the first failing command:
1. **Horizon ring.** 360 tick marks in one `engrave_scale` call (majors every 10 degrees, half-length marks every 5), 24 numbers and the 12 zodiac signs, one `engrave` call each.
2. **Meridian ring.** A quadrant-mirrored 0-90 scale and 40 numbers.
3. **Union.** An exact `boolean` union of the two engraved rings, with `manifold: true`.
4. **Materials.** `brass` with `age: aged` and `scratch_direction: v`, which follows both rings along their paths, and `marble`.

`summary.json` shows that every cut left the mesh closed, with no slivers, and which solver the union used.

## Noise terrain

`noise_terrain.py` builds a 2 x 2 set of 100 m terrain tiles with ridged, domain-warped noise and a rock made with `noise_displace` on a subdivided ico sphere, with commands only, and renders close-ups. It is the acceptance build of the `noise-terrain` job.

```
blender --background --factory-startup --python docs/examples/noise_terrain.py -- out
```

The script writes into `out`:
- `noise-terrain.blend`;
- five PNGs: `overview` (shaded), `overview-clay`, `ridge-detail`, `tile-joint` (clay, at the corner where the four tiles meet) and `rock`;
- `summary.json`: every command with its time, mesh size and height range.

It runs these steps in order, and stops at the first failing command:
1. **Tiles.** Four `heightfield` calls with the same seed and noise (`mode` ridged, `hurst` 0.7, `scale` 150 m, seven octaves, a 45 m warp) and tiles `[0, 0]` to `[1, 1]`, each with a skirt, so they join along their edges and close into solids. The finest wavelength (150 / 2^6 = 2.3 m) is more than two vertex spacings (1 m).
2. **Rock.** An ico sphere flattened with `transform` and `apply_transform`, then three `noise_displace` passes: billow lumps at 2.6 m, worley ridged cracks at 1.1 m, and fine perlin grain at 0.3 m.
3. **Materials and renders.** Stone presets, then the five renders.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Scatter rocks

`scatter_rocks.py` scatters a rock set over a 100 m `heightfield` tile with commands only and renders it. It is the acceptance build of the `scatter` job.

```
blender --background --factory-startup --python docs/examples/scatter_rocks.py -- out
```

The script writes into `out`:
- `scatter-rocks.blend`;
- four PNGs: `overview`, `slope` and `closeup` (shaded), and `top` (clay, looking straight down, where the spacing shows);
- `summary.json`: every command with its time and, for `scatter`, the count, the smallest pairwise distance, the masked-out share and the fitted exponent.

It runs these steps in order, and stops at the first failing command:
1. **Terrain.** One `heightfield` tile with a skirt and the `slope` and `height` attributes, and a ground material.
2. **Rocks.** Three ico spheres, each flattened, shaped by three `noise_displace` passes and given its base at the origin with `set_origin` to `bottom_centre`, so the origin is the point that touches the ground.
3. **Scatter.** One `scatter` call with the three rocks as `sources`, `min_distance` 0.6 m (the 2 m rock footprint at the smallest scale 0.3), a `slope` mask that keeps faces up to 38 degrees, a `power` size distribution with exponent -2 from scale 0.3 to 2.4, `align` blend, a 6 degree tilt and an `embed` of 0.22. The source rocks are deleted afterwards; the copies keep sharing their meshes.
4. **Renders.** Four views.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Phyllotaxis

`phyllotaxis.py` builds a sunflower head, a pine cone and a succulent rosette with commands only, with materials, and renders close-ups. It is the acceptance build of the `phyllotaxis` job.

```
blender --background --factory-startup --python docs/examples/phyllotaxis.py -- out
```

The script writes into `out`:
- `phyllotaxis.blend`;
- seven PNGs: `sunflower`, `sunflower-seeds`, `pine-cone`, `pine-cone-top`, `rosette`, `rosette-top` and `overview`;
- `summary.json`: every command with its time and, for `instances`, the count, the divergence and the area per organ.

It runs these steps in order, and stops at the first failing command:
1. **Materials.** `soil`, a yellow `leaf` for petals, dark `dirt` seeds, `bark` for the scales and a pale green `leaf` for the succulent.
2. **Organs.** Each organ (a seed, a petal, a cone scale, a rosette leaf) is built once with `mesh_from_data`: a lens-shaped blade with its base at the origin, its length along X and UVs over the unit square, so the leaf veins follow it.
3. **Sunflower.** 1,100 seeds on a `disc` (`c` 4.2 mm, `golden`), each growing from 55 % of its size with the index (`scale_by_age`); then two rings of petals through the same disc with `start` 1100 and 1500, so they sit just outside the last seeds, opening wider with the index (`tilt_by_age`) and with a seeded `jitter`.
4. **Pine cone.** 89 scales on a `cone` (radius 3.6 cm, height 10 cm), growing from 40 % with the index and opening from 6 to 40 degrees towards the base, over a bark core cone.
5. **Rosette.** 89 leaves on a `sphere` cap of `polar_extent` 112 degrees, small and upright at the heart and larger and open at the edge, around a sphere.
6. **Renders.** Seven views.

`BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Natural dressing

`natural_dressing.py` dresses the terrain and rock of `noise_terrain.py` with natural materials, with commands only, and renders close-ups. It is the acceptance build of the `natural-materials` job.

```
blender --background --factory-startup --python docs/examples/natural_dressing.py -- out
```

It adds to the terrain and rock:
- **Soil with moss.** `soil` on the terrain, and a `moss` layer through `up_facing`, `slope` (at most 38 degrees from horizontal) and `noise` masks combined with `with_masks`, so moss grows in patches on the gentle, upward-facing ground.
- **Stone without patches.** `stone` on the rock with its default soft colour patches, and a moss layer on its top.
- **A bark log** (`bark`, grain along the cylinder axis) and **a leaf card** (`leaf` with `cutout`, from its UV square). They stand at y -30, beside the terrain tiles and not in front of them: the 110 m tall terrain shades anything close behind it in the preview light, which made the log close-up almost black.

The close-ups are `rock`, `rock-top`, `log`, `leaf`, `ground-close` and the overview views of `noise_terrain.py`.

## Eroded terrain

`eroded_terrain.py` builds a 2 x 2 set of 100 m tiles from `heightfield`, erodes them as one grid with `erode` (hydraulic droplets, then thermal talus slides), dresses them with one `material_nodes` graph masked by the `slope`, `erosion` and `deposition` attributes, and renders them in low sun, with commands only. It is the acceptance build of the `erode` job.

```
blender --background --factory-startup --python docs/examples/eroded_terrain.py -- out
```

The script writes into `out`:
- `eroded-terrain.blend`;
- five PNGs: `overview` and `channels` (shaded and clay, from a camera and a low sun) and `tile-joint-clay` (the corner where the four tiles meet);
- `summary.json`: the `erode` reply (volumes eroded, deposited and carried off the edge, thermal sweeps, time) and every command with its time.

It runs these steps in order, and stops at the first failing command:
1. **Tiles.** Four `heightfield` calls with the same seed and gentle fBm (`scale` 140 m, five octaves, `hurst` 0.9, 35 m of height), tiles `[0, 0]` to `[1, 1]`, with `slope` and `height` attributes. The relief is gentle on purpose: slopes well below the talus angle leave the droplets room to cut gullies, and the thermal sweeps then only trim their walls.
2. **Erosion.** One `erode` call with `name` and the other three tiles in `names`: 300,000 droplets (capacity 3, `erode_rate` 0.02, `deposit_rate` 0.1, `inertia` 0.1, 200 steps of 1 m, the smallest brush) in 20 rounds, each followed by thermal sweeps at a 40 degree talus angle. The outer edge of the 200 m grid stays as built; the three inner edges are eroded as part of the grid and the tiles still share them exactly (`edge_change` 0).
3. **Materials.** The tiles are joined and welded along their shared edges (so shading has no seam), then one `material_nodes` graph mixes soil towards rock where `slope` is steep, towards pale scoured rock where `erosion` is deep and towards silt where `deposition` is thick.
4. **Renders.** A sun at 25 degrees, a world colour and three cameras, then the five renders.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_DROPLETS`, `BLENDWORKS_SWEEPS`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.
## Shells

`shells.py` builds three shells with commands only, gives each a material and renders them. It is the acceptance build of the `shell` job.

```
blender --background --factory-startup --python docs/examples/shells.py -- out
```

The script writes into `out`:
- `shells.blend`;
- four PNGs: `overview` and one close-up each of `conch`, `ammonite` and `ribbed_fan`;
- `summary.json`: every command with its time and, for `shell`, whether the result is manifold, its volume and the thinnest wall.

It runs these steps in order, and stops at the first failing command:
1. **Scene.** A sky, a sun and a concrete floor.
2. **Conch.** A high spire: `W` 1.42, `D` 0.15, `T` 0.9 over 6.5 whorls on an ellipse profile, 14 ribs per whorl, a flared lip and a 2 mm hollow wall.
3. **Ammonite.** A flat coil: `W` 1.9, `D` 0.5, `T` 0 over 4 whorls on a tall ellipse, 18 ribs per whorl and a 3 mm wall, in a marble preset in metres.
4. **Ribbed fan.** A flat fan like a scallop valve, but one piece and without ears or a hinge: an arched plate profile given as points, `W` 3 over half a whorl, with 28 radial ribs.
5. **Materials and renders.** Each shell gets a stone or marble preset, its origin is set to the bottom centre, then the four renders.

`BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Grow trees

`grow_trees.py` grows three tree skeletons with roots by commands only and renders them. It is the acceptance build of the `tree-skeleton` job.

```
blender --background --factory-startup --python docs/examples/grow_trees.py -- out
```

The script writes into `out`:
- `grow-trees.blend` and `grow-trees.glb`, whose three tree nodes carry their skeletons in `extras.blendworks_skeleton`;
- seven PNGs: `oak`, `conifer` and `windswept` (side views, shaded, roots included), `oak_top` and `conifer_top` (clay, looking straight down), `oak_base` (the trunk base and the roots) and `row` (all three);
- `summary.json`: every command with its time and, for `grow_tree`, the node, tip, branching and root counts, the height, spread, root depth, base radius, largest pipe-model error and the growth report.

It runs these steps in order, and stops at the first failing command:
1. **Oak.** Space colonisation in a hemispherical crown 5.5 m wide from 2.6 m to 10 m, 4000 points, `influence` 1.6 m, `kill` 0.36 m, `step` 0.18 m and a slight upward tropism, with roots in a soil envelope 1.4 m deep and 3.2 m wide.
2. **Conifer.** Weber–Penn levels: a 14 m trunk in a conical shape with 70 branches that turn by 137.5 degrees, each with up to 16 twigs, branches at 84 degrees curving up by 24 degrees, `taper` 0.55 and `ratio_power` 0.9, with roots.
3. **Windswept.** A UV sphere stretched and tilted downwind is the crown envelope (a mesh envelope); colonisation with a tropism of `[0.45, 0, -0.08]` leans the trunk and streams the branches downwind; the roots lean upwind. The envelope is deleted afterwards.
4. **Material, files and renders.** The `bark` preset of `material_procedural` on all three, the `.blend` and `.glb`, then the renders.

`BLENDWORKS_TREE_DETAIL` (a factor on the point and branch counts), `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Rocks

`rocks.py` builds a fractured boulder with its fragments, a chipped block and three worn stones with commands only, renders them and exports each stone. It is the acceptance build of the `rocks` job.

```
blender --background --factory-startup --python docs/examples/rocks.py -- out
node src/judge/bin.js judge out/rock.spec.json out/stone_a.glb --preview
```

The script writes into `out`:
- `rocks.blend`, `stone_a.glb`, `stone_b.glb`, `stone_c.glb` and `rock.spec.json` (the `natural` rock rules with their calibrated defaults);
- three PNGs: `overview`, `boulder` (the fragments, apart) and `stones`;
- `summary.json`: every command with its time and mesh size.

It runs these steps in order, and stops at the first failing command:
1. **Boulder.** A cube of 2.2 x 1.5 x 1.3 m, chipped 14 times (30 cm to 50 cm deep) into an irregular convex block, then `fracture` (binary, 11 pieces, `min_size` 15 cm). Each fragment is pushed outward and tumbled by a few degrees. The cut faces share a light `fresh_rock` material through `fresh_material`.
2. **Chipped block.** A cube with `chip` (10 chips, 30 cm deep): fresh, blocky and closed.
3. **Worn stones.** Each is an ico sphere cut once by `fracture` (the larger piece is kept), then `chip` knocks corners off, `abrade` rounds the edges (amount 0.8 to 1) so the rim of the cut is a smooth fillet, and three `noise_displace` layers in metres follow: vertical lumps (`direction` z, 18 % of the size, which cannot tear the rim), ridged worley cracks (2 %) and fine grain (3 %). Then UVs, the `granite` material and a baked base colour.

`BLENDWORKS_SHOT_SIZE`, `BLENDWORKS_SHOT_SAMPLES`, `BLENDWORKS_BAKE_SIZE` and `BLENDWORKS_FRAGMENTS` make a smaller, faster run. The judge scores of the three stones against the calibrated rock defaults are measured by `test/rocks-example.test.ts`.

## L-system plants

`lsystem_plants.py` grows four kinds of plant from the presets of *The Algorithmic Beauty of Plants* by commands only, gives them leaf and flower organs and materials, and renders them. It is the acceptance build of the `lsystem` job.

```
blender --background --factory-startup --python docs/examples/lsystem_plants.py -- out
```

The script writes into `out`:
- `lsystem-plants.blend` and `lsystem-plants.glb`, whose six plant nodes carry their skeletons in `extras.blendworks_skeleton`;
- five PNGs: `herb`, `bushes` (the three stochastic bushes side by side), `tree`, `fern` and `overview` (all of them);
- `summary.json`: every command with its time and, for `lsystem`, the node, branching and organ counts, the height, the spread and the derivation report.

It runs these steps in order, and stops at the first failing command:
1. **Materials, ground and organs.** Procedural `leaf`, `bark`, `soil` and petal presets; a leaf and a flower made for each plant with `mesh_from_data`, `instances` (petals on a circle, realised) and `join`.
2. **Herb.** `bush_1_25` (figure 1.25) for 5 steps: three branches at every apex, leaves on the internodes and a yellow flower at every apex.
3. **Bushes.** `stochastic_1_27_leafy` (figure 1.27 with leaves and a flower) in seeds 4, 7 and 12: three plants that differ in their branching and belong to one species.
4. **Tree.** `monopodial_2_6a` (figure 2.6, table 2.1) with leaves at the apices B and C whose size follows the branch length (`scale_by_parameter`).
5. **Compound leaf.** `compound_leaf_5_11b` (figure 5.11b) with a small leaflet at every apex.
6. **Files and renders.** The `.blend`, the `.glb` and the five renders.

`BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Tree meshes

`tree_meshes.py` turns the oak, conifer and windswept skeletons of `grow_trees.py` (it imports that script and grows the same three trees) into bark meshes with leaves, by commands only, and renders them. It is the acceptance build of the `tree-mesh` job.

```
blender --background --factory-startup --python docs/examples/tree_meshes.py -- out
```

The script writes into `out`:
- `tree-meshes.blend` and `tree-meshes.glb`, whose three bark nodes carry their skeletons in `extras.blendworks_skeleton`;
- nine PNGs on a soil ground: `oak`, `conifer` and `windswept` (each tree), `row` (all three), `oak_base` and `windswept_base` (the flared base), `oak_bark` and `conifer_bark` (bark close-ups) and `oak_fork` (the junctions where the oak's trunk forks);
- `summary.json`: every command with its time and, for `tree_mesh` and `tree_leaves`, the triangles, the closed-shell report, the self-intersections, the materials and the leaf counts.

It runs these steps in order, and stops at the first failing command:
1. **Skeletons.** The three `grow_tree` calls of `grow_trees.py`.
2. **Materials.** `bark` (the preset in UV coordinates with the grain along `v`, so it follows every branch in metres), a darker `roots`, `fresh_wood` for cut ends, `leaf` with its cut-out and translucency, `needles` and `soil`.
3. **Bark.** `tree_mesh` on each skeleton with the default `skin` junction, a stronger trunk flare gathered towards the roots and swollen root bases; the conifer drops its twigs under 4 mm, which end in fresh wood.
4. **Leaves.** `tree_leaves` puts clusters of 9 cm leaves on the oak and of 8 cm leaves turned towards a low sun on the windswept tree, and (layout `single`) a needle cluster (nine needles in the golden angle, built with `mesh_from_data`) along the two outer orders of the conifer.
5. **Files and renders.** The `.blend` and `.glb`, then a ground plane and the renders.

`BLENDWORKS_TREE_DETAIL` (a factor on the point and branch counts), `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Tree shapes

`tree_shapes.py` grows, meshes and leafs a weeping willow, a gnarled old oak and a wind-bent coastal tree from the three `grow_tree` form presets, by commands only, and renders them. It is the acceptance build of the `tree-shape` job.

```
blender --background --factory-startup --python docs/examples/tree_shapes.py -- out
```

The script writes into `out`:
- `tree-shapes.blend` and `tree-shapes.glb`, whose three bark nodes carry their skeletons in `extras.blendworks_skeleton`;
- five PNGs on a soil ground: `willow`, `oak` and `coastal` (each tree), `row` (all three, the wind blowing to the right) and `oak_trunk` (the crooked trunk);
- `summary.json`: every command with its time; for `grow_tree` the node counts, the pipe-model error and the growth report with its `form` (kinks, largest gnarl offset, largest sag curvature, pruned nodes); for `tree_mesh` and `tree_leaves` the triangles, the closed-shell report and the leaf counts.

It runs these steps in order, and stops at the first failing command:
1. **Skeletons.** `grow_tree` with `preset` `weeping_willow` (levels; the outer orders hang by gravitropism), `gnarled_oak` (colonisation with gnarl, kinks, a twisting trunk, upward phototropism and sag under the limbs' own weight) and `windswept_coastal` (colonisation bent by a wind along +X), each with roots.
2. **Materials.** `bark`, `roots` and `fresh_wood` as in `tree_meshes.py`, `leaf` and a yellower `willow_leaf`, both cut out, and `soil`.
3. **Bark.** `tree_mesh` on each skeleton with the `skin` junction and flared bases; the willow's twigs under 4 mm become bark cards.
4. **Leaves.** `tree_leaves` in leaf clusters: the willow and the oak take the foliage and leaf material of their species (the presets map to `willow` and `oak`); the coastal tree gets 7 cm leaves in clusters turned towards a low sun.
5. **Files and renders.** The `.blend` and `.glb`, then a ground plane and the renders.

`BLENDWORKS_TREE_DETAIL` (a factor on the attraction point counts; below 1 the leaves are built at `detail` `low`), `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run.

## Tree species

`tree_species.py` grows, meshes and leafs the six species presets (oak, birch, pine, willow, maple and olive) in a row, by commands only, measures each crown and renders each tree at mid and close range. It is the acceptance build of the `tree-realism` job.

```
blender --background --factory-startup --python docs/examples/tree_species.py -- out
```

The script writes into `out`:
- `tree-species.blend`;
- twelve PNGs, `<species>_mid` (the whole tree) and `<species>_close` (a part of the crown at about a quarter of the tree's height across);
- `summary.json`: every command with its time; for `grow_tree` the node counts and the strand statistics, for `tree_mesh` the closed-shell report, for `tree_leaves` the clusters, leaves, per-leaf `variation`, `foliage` (leaf area, density and index) and `crown` (the measured fill and its band).

It runs these steps in order, and stops at the first failing command:
1. **Skeletons.** `grow_tree` with each species preset, 26 m apart.
2. **Bark.** `tree_mesh` with the species' flare and bark material, or a scanned bark (below).
3. **Leaves.** `tree_leaves` with the species' clusters, leaves and leaf material and `measure`.
4. **Renders.** An HDRI if given, a soil ground and the renders.

`BLENDWORKS_HDRI` names an HDRI inside `out` for the world. `BLENDWORKS_SCANNED_BARK` names scanned bark folders inside `out` (Poly Haven layout: `<folder>/<asset>_diff_2k.jpg`, `_rough_`, `_nor_gl_`, `_disp_`), either one for every tree or `species=folder` entries separated by `;`. `BLENDWORKS_TREE_DETAIL` (a factor on attraction points or first-level branches), `BLENDWORKS_MEASURE_CROWNS=0`, `BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make a smaller, faster run; below a detail of 1 the leaves are built at `detail` `low`.

## Characters

`characters.py` builds a stylised humanoid, a four-legged fox and a treasure chest from primitives and shape tools, rigs, skins and animates them, exports each and writes a judge spec for each, by commands only. It is the acceptance build of the `rig-animation` job; the models are in `character_models.py`.

```
blender --background --factory-startup --python docs/examples/characters.py -- out
node src/judge/bin.js judge out/hero.spec.json out/hero.glb --out out/report-hero
node src/judge/bin.js judge out/fox.spec.json out/fox.glb --out out/report-fox
node src/judge/bin.js judge out/chest.spec.json out/chest.glb --out out/report-chest
```

The script writes into `out`:
- `hero.glb`, `fox.glb` and `chest.glb` (and a `.blend` of each), every clip a named glTF animation;
- `hero.spec.json`, `fox.spec.json` and `chest.spec.json`: the size, the `rig` rules with a `boneMap` from the template's bone map, the `skin` rules (at most 4 influences, none unweighted, normalised, rest pose), the `animation` rules (required clips, seamless loops, at most 4 s, root motion under 5 cm for the in-place clips, bounds within the size over every frame) and the glTF validator with 0 errors and 0 warnings;
- animation frames as PNGs, named `<asset>-<clip>-<frame>-<view>.png`: eight walk frames of the hero and six trot frames of the fox from the side and the front, two idle frames of each from three-quarter, and four frames of the chest opening;
- `summary.json`: every command with its time and, for `rig_template`, `skin_bind`, `animation_preset` and `export`, the bone count, the weights report, the stride, speed, cadence and hip drop, and the exported armatures.

It runs these steps for each asset, in a new scene, and stops at the first failing command:
1. **Model.** The hero (1.76 m) is a `lathe` torso flattened front to back, `sweep` legs and arms whose paths are rounded at the knees and elbows so they bend smoothly, sphere head, hands and eyes, and box shoes, joined into a body, a legs and an arms mesh. The fox is a `lathe` body lying along Y, `sweep` neck, snout, legs and tail, a sphere skull, cone ears and flattened sphere paws, joined into a body and a legs mesh. The chest is a box and a lid with iron bands and a lock.
2. **Rig.** `rig_template` humanoid, quadruped or hinge, fitted to the meshes with landmarks at the joints the models were built around.
3. **Skin.** `skin_bind` with automatic weights per mesh, limited to the bones that mesh should follow (`bones`), smoothed twice; the head, eyes, hands and paws are rigid parts picked with `near`. The chest binds with no automatic weights: its loose parts go rigidly to `Base` or `Lid`.
4. **Animate.** `animation_preset` walk and idle for the hero, trot and idle for the fox, open (105°, 48 frames) for the chest. All loop seamlessly in place.
5. **Export, frames and spec.** `export` writes the glb with its armature, `clip_pose` and `render_preview` take the frames, and the spec goes next to the glb.

`BLENDWORKS_SHOT_SIZE` and `BLENDWORKS_SHOT_SAMPLES` make smaller, faster renders, `BLENDWORKS_CHARACTER_SHOTS=0` skips them, and `BLENDWORKS_CHARACTERS` (for example `hero,chest`) builds only some assets. `test/characters-example.test.ts` runs the script and judges the three assets.

## Meadow cover

`meadow_cover.py` dresses a meadow with grass, flowers and litter with commands only, and renders it before and after. It is the acceptance build of the `ground-cover` job.

```
blender --background --factory-startup --python docs/examples/meadow_cover.py -- out
```

The script writes into `out`:
- `meadow-cover.blend` and `meadow-cover.glb` (the cover as `EXT_mesh_gpu_instancing` instances with the wind colours);
- four PNGs: `eye-before` and `eye-after` (an eye-level close-up at 0.9 m), `wide-before` and `wide-after` (a raised wide shot of the tree, the rocks and the hill);
- `summary.json`: every command with its time and, for `ground_cover`, the instance count, the budget, the near distance, the count per population and the mean of the contact attribute, and for each render the mean, spread and greenness of the lower half of the image.

It runs these steps in order, and stops at the first failing command:
1. **Terrain.** A 40 m `heightfield` tile with the `grass_ground` material: the textured plane of the "before" renders.
2. **Tree.** A `gnarled_oak` from `grow_tree`, `tree_mesh` and `tree_leaves`.
3. **Rocks.** Three noise-displaced rocks scattered with a power-law size distribution, as in the scatter example.
4. **Before.** The two cameras, a sun and a sky, and two renders.
5. **Cover.** One `ground_cover` call with the `meadow` preset, the eye camera as the falloff centre (full density to 10 m), the trunk and the rocks as obstacles, the trunk as the tree for the litter, and the wind colours.
6. **After.** The same two renders, the instanced glb and the `.blend`.

`BLENDWORKS_TERRAIN_RESOLUTION`, `BLENDWORKS_SHOT_SIZE`, `BLENDWORKS_SHOT_SAMPLES`, `BLENDWORKS_TREE_DETAIL` and `BLENDWORKS_COVER_BUDGET` make a smaller, faster run. `test/meadow-cover-example.test.ts` runs it small, checks the budget and the renders, and validates the glb with the Khronos glTF validator.

## Weather scene

`weather_scene.py` builds an outdoor scene with Blendworks commands only and renders it under several weathers and times of day. It is the acceptance scene of the `sky-weather` job.

```
blender --background --factory-startup --python docs/examples/weather_scene.py -- out [presets] [times]
```

- The scene: a 100 m meadow `heightfield` on a 6 km plain to the horizon, a dry-stone wall of chipped and abraded stones placed with `instances`, an oak (`grow_tree` preset `oak`, `tree_mesh`, `tree_leaves`), `ground_cover` with the `meadow` preset and an eye-level camera. It is saved as `weather-scene.blend` and reused by later runs.
- `presets` (default `clear,fair_cumulus,overcast,heavy_rain,thunderstorm`) and `times` (default `noon,golden_hour`) are comma-separated; each pair is one `weather` call and one `render_final` into `<preset>-<time>.png`.
- `summary.json` holds each shot's storm value, sun, lamp, cover, rain, lightning, exposure, cloud form and sampling time.
- `BLENDWORKS_SHOT_WIDTH`, `BLENDWORKS_SHOT_HEIGHT`, `BLENDWORKS_SHOT_SAMPLES`, `BLENDWORKS_SHOT_SECONDS`, `BLENDWORKS_TREE_DETAIL`, `BLENDWORKS_COVER_BUDGET` and `BLENDWORKS_CLOUD_FORM` make a smaller, faster or cheaper run; `BLENDWORKS_DEVICE` picks the device.

## Liquid scenes

`liquid_lake.py` and `liquid_still_life.py` build the two acceptance scenes of the `liquids` job with Blendworks commands only and render them with `render_final`.

```
blender --background --factory-startup --python docs/examples/liquid_lake.py -- out
blender --background --factory-startup --python docs/examples/liquid_still_life.py -- out
```

- `liquid_lake.py`: rolling land (a 300 m `heightfield` at 1 m, inside three rings of coarser tiles out to 4 km that sample the same noise, all raised by one `noise_displace` layer of hills 2.5 km across, so the land runs on to hills at the horizon), `weather` `fair_cumulus` in the afternoon, a lake at the spill level of the lowest hollow (`liquid_body` kind `lake`), a river from the source with the gentlest flow among those whose lowest line drains into the lake (`liquid_body` kind `river`, tried without carving, then built with its channel carved), boulders (ico spheres chipped, abraded and displaced, stone with lichen on top) scattered along the water line of the lake and the river with the `shore` mask (2.5 m above to 0.3 m under the water line, grouped by a noise mask, wet where the water reaches), trees near the river mouth (`grow_tree` species presets, `tree_mesh`, `tree_leaves`), `ground_cover` with the `meadow` preset and a `shore` population of reeds over everything the two shots see, haze, a main shot across the lake to the river mouth from a rise of the land and a close shot of the rocks at the water line. It writes `lake.png`, `rocks.png`, `liquid-lake.blend` and `summary.json` (the lake's level, area, volume, wind, waves and wet shore, the river's length, speed and junction, the rocks' count and how far they reach above and under the water line, and the render's liquid settings).
- `liquid_still_life.py`: lathed glasses of water, red wine (a stemmed glass), milk and olive oil and a jar of honey, filled with `liquid_fill` (`glass` true), and a coffee spill on an oak table (a film at the receding contact angle of 35°, 1.5 mm thick, with a darker ring at its edge) in front of a dark wall, lit by a window light from behind and soft fills. It writes `still-life.png`, `liquid-still-life.blend` and `summary.json`.
- `BLENDWORKS_SHOT_WIDTH`, `BLENDWORKS_SHOT_HEIGHT`, `BLENDWORKS_SHOT_SAMPLES`, `BLENDWORKS_SHOT_SECONDS`, `BLENDWORKS_DEVICE` set the render; the lake also takes `BLENDWORKS_TREE_DETAIL`, `BLENDWORKS_TREES`, `BLENDWORKS_COVER_BUDGET`, `BLENDWORKS_CLOUD_FORM` and `BLENDWORKS_TERRAIN_SEED`, and the still life `BLENDWORKS_LATHE_SEGMENTS`.

## World scale

`world_scale.py` builds a landscape at world scale with Blendworks commands only. It is the acceptance scene of the `world-scale` job.

```
blender --background --factory-startup --python docs/examples/world_scale.py -- out
```

- The plan: a clear golden-hour sky, a grass and rock material, and 64 `heightfield` tiles in four nested rings (2, 6, 18 and 36 km tiles, each ring leaving out the block the ring inside covers), so the land is one surface from the camera to 108 km out in every direction.
- The whole plan, about 200 calls, goes through `validate` first; the script stops with every problem if it finds any, and runs nothing.
- The camera stands on a ridge 15 km from the origin, 30 m above the ground, with clip distances up to 300 km. `atmosphere` fills the scene with haze of 70 km visibility, so the far ranges fade into the sky, and `render_final` renders the view.
- `summary.json` holds the camera's place and distance from the origin, the number of tiles and how far the land reaches, the haze settings and box, and each command with its time.
- `BLENDWORKS_WORLD_DETAIL` scales every tile's resolution (default 1.0). `BLENDWORKS_SHOT_WIDTH`, `BLENDWORKS_SHOT_HEIGHT`, `BLENDWORKS_SHOT_SAMPLES`, `BLENDWORKS_SHOT_SECONDS` and `BLENDWORKS_DEVICE` set the render. `test/world-scale-example.test.ts` runs it with tiny tiles and a 64 px render.
