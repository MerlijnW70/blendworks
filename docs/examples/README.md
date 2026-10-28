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
