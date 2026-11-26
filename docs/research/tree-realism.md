# Trees that pass for photographs

The trees of the earlier presets read as computer graphics in a scene with an HDRI sky and scanned textures: crowns too sparse, leaves too large and identical, one leaf texture, no small leaf clusters at the twigs, and a weeping willow whose strands hung evenly spaced and equally long, like a comb. This note records what was measured, what was changed and where the numbers come from. The design is in `docs/DESIGN.md` (Tree skeletons, Tree meshes); the job is `jobs/tree-realism/SPEC.md`.

## Sources

- [S1] P. Prusinkiewicz and A. Lindenmayer, *The Algorithmic Beauty of Plants*, 1990: tropism (2.1), phyllotaxis.
- [S2] A. Runions, B. Lane, P. Prusinkiewicz, "Modeling trees with a space colonization algorithm", Eurographics Workshop on Natural Phenomena, 2007.
- [S3] J. Weber and J. Penn, "Creation and rendering of realistic trees", SIGGRAPH 1995: the variation parameters `nLengthV`, `nDownAngleV`, `nRotateV` that `length_variation`, `down_angle_variation` and `rotate_variation` follow.
- [S53] C. Eloy, "Leonardo's rule, self-similarity and wind-induced stresses in trees", Physical Review Letters 107, 2011: the Leonardo band the judge uses.
- [T1] G. P. Asner, J. M. O. Scurlock, J. A. Hicke, "Global synthesis of leaf area index observations", Global Ecology and Biogeography 12, 2003: leaf area index of temperate broadleaf and needleleaf forests mostly between 2 and 8.
- [T2] N. J. J. Bréda, "Ground-based measurements of leaf area index: a review of methods, instruments and current controversies", Journal of Experimental Botany 54, 2003: gap fraction, one minus the share of sight lines the canopy stops, as the measured quantity behind optical LAI; the crown fill below is that quantity seen from the side.
- [T3] Ü. Niinemets, "A review of light interception in plant stands from leaf to canopy in different plant functional types and in species with varying shade tolerance", Ecological Research 25, 2010: sun leaves at the crown surface are smaller and steered towards the light, shade leaves inside larger; the sun bias of outer clusters and `shade_growth` follow it.
- [T4] S. Jacquemoud and S. Ustin, *Leaf Optical Properties*, Cambridge University Press, 2019: a leaf transmits a large share of the light it does not absorb, diffusely and tinted green to yellow, and the abaxial side is paler; hence the thin-walled subsurface translucency, the tint and the underside colour of the `leaf` preset.
- [T5] Poly Haven (CC0): the scanned and modelled trees `island_tree_01`, `island_tree_02`, `island_tree_03`, `jacaranda_tree`, `fir_tree_01`, `pine_tree_01`, `tree_small_02` and `searsia_lucida` (https://polyhaven.com/a/<asset>), used for the crown fill band, and the bark scans used in the proof renders: `jolcham_oak_bark_01`, `pine_bark`, `bark_willow`, `trident_maple_bark`, `tree_bark_03`.

No tree generator's code was read or copied; the clusters, hem, sway, strand statistics and crown fill are ours, written from the sources above and from observation of the reference photos.

## Reference photos (CC0)

All from Wikimedia Commons; each was checked through the Commons API (`extmetadata.LicenseShortName`) to read `CC0`, and each was looked at to confirm the season (leaves on, summer) and the whole tree:

| Species | Photo | Author | Note |
|---|---|---|---|
| oak, Quercus robur | https://commons.wikimedia.org/wiki/File:Kirchheim,_Landesgartenschau,_quercus_robur,_3.jpeg | Renardo la vulpo | October, in leaf |
| birch, Betula pendula | https://commons.wikimedia.org/wiki/File:20120919Malus_%26_Betula_pendula.jpg | AnRo0002 | September, in leaf; trunk close-up with horizontal black lenticels https://commons.wikimedia.org/wiki/File:Part_of_birch_trunk_in_Norrkila.jpg (W.carter, CC0) |
| pine, Pinus sylvestris | https://commons.wikimedia.org/wiki/File:Grimberg_natural_monument_Scots_pine_(Pinus_sylvestris)_panorama.jpg | Pinecone23 | May 2025: straight bole, plated reddish bark, tiered crown of needle masses; bark close-up https://commons.wikimedia.org/wiki/File:Bark_of_Grimberg_natural_monument_Scots_pine_(Pinus_sylvestris).jpg |
| willow, Salix x sepulcralis (weeping willow) | https://commons.wikimedia.org/wiki/File:Zoo_salix_sepulcralis_chrysocoma.jpg | Bert76 | July 2024, in full leaf: steep ascending limbs, a dome of long hanging strands to the ground (replaces a December photo of a leafless tree) |
| maple, Acer pseudoplatanus (sycamore maple; no CC0 photo of Acer platanoides in leaf was found) | https://commons.wikimedia.org/wiki/File:Bergahorn_von_Molln.jpg | Daniel Mietchen | 27 July 2024, in full leaf (replaces a March photo of a leafless tree) |
| olive, Olea europaea | https://commons.wikimedia.org/wiki/File:Oxford_Radcliffe_Camera_Palestinian_olive_tree_encampment_01.jpg | Kiri of Karitane | a young olive in leaf |

The Poly Haven trees of [T5] are three-dimensional references at the same time: rendered next to a preset under the same HDRI they show crown density and leaf scale directly.

## Crown fill, calibrated

`tree_leaves` with `measure` renders the crown from the judge's front, back, left and right views and reports `fill`, the mean cover inside the crown silhouette (`docs/DESIGN.md`, Tree meshes). `calibrate_crowns.py` here measures the Poly Haven trees the same way (LOD0, every whole tree in each file):

```
blender --background --factory-startup --python docs/research/tree-realism/calibrate_crowns.py -- <models folder> crown-fill.json
```

`crown-fill.json` holds the result. Twelve trees: mean 0.568, standard deviation 0.080, smallest 0.374 (a sparse young fir), largest 0.671. The broadleaves lie between 0.575 and 0.636, the pines near 0.5. The band in `bridge/blendworks_bridge/tree_crown.py` is the mean ± 2 standard deviations, [0.41, 0.73]; `test/tree-realism-docs.test.ts` fails when it no longer matches this file.

| Tree | Fill |
|---|---|
| island_tree_01, 02, 03 | 0.624, 0.636, 0.617 |
| jacaranda_tree | 0.593 |
| searsia_lucida | 0.575 |
| tree_small_02 | 0.606 |
| fir_tree_01 a, b, c | 0.671, 0.617, 0.374 |
| pine_tree_01 a, b, c | 0.503, 0.488, 0.511 |

The presets, measured at full size with seed 1 (`fill`): oak 0.687, birch 0.463, pine 0.660, willow 0.657, maple 0.697, olive 0.689. A crown with one or two leaves per cluster every 1.5 m measures below 0.41 (bridge test `test_tree_crown.py`).

## Side by side with the references

The renders of each preset at mid and close range under the `sunset_meadow_path` HDRI, next to the reference photo, are the delivery's proof (`docs/examples/tree_species.py` renders the same views). The pine and willow were changed in the third round until they read as the photographed trees from both distances.

## Hanging strands

`growth.strands` of `grow_tree` (`docs/DESIGN.md`, Tree skeletons) on the willow, seed 7:

| | spacing_cv | neighbour_length_change | branched_share | lean_spread |
|---|---|---|---|---|
| `weeping_willow` before this change | 0.001 | 0.046 | 0.014 | 3.8° |
| `weeping_willow` now | 0.35 | 0.22 | 0.43 | 6.6° |
| `willow`, taller and wider (third round) | 0.37 | 0.19 | 0.24 | 10.4° |
| `willow` with the variation, kinks, sway and hem variation set to 0 | 0.001 | 0.057 | 0 | |

The thresholds of `irregular` (0.3 and 0.15) sit between the comb and the presets; an even comb is at 0 by construction and uniform random spacing within slots of half-width 0.45 gives about 0.37.


## Foliage-only fill and the species floors

`fill` counts bark, twigs and leaves and hardly moves when leaves are taken away: a crown with half its leaves still measures within a tenth of the full one. `foliage_fill` is the same measure from a second render in which every material but the leaf material is clear, over the silhouette of the whole tree. The same twelve scans were measured that way (leaf materials `*_leaves`, and the conifers' needle cards `*_twig`): mean 0.486, deviation 0.085, from 0.314 to 0.647, the band [0.317, 0.655] (`calibrate_crowns.py`, `crown-fill.json`; `test/tree-realism-docs.test.ts` checks both bands against the file).

Presets at full size, seed 1 (`foliage_fill`, then with about half the leaves and twice the spacing): oak 0.624 (0.450), birch 0.424 (0.227), pine 0.618 (0.437), willow 0.580 (0.329), maple 0.583 (0.377), olive 0.623 (0.359). `tree_species.FILL_FLOOR` holds each preset's value less 0.08; the thinned presets all fall below it, by 0.17 to 0.27, and the bridge tests `test_tree_crown.py` and `test_tree_crown_species.py` assert that for each species right after measuring its preset, so each preset is rendered once.

Leaf area index of the presets, same runs: oak 3.7, birch 2.2, pine 4.0, willow 2.7, maple 2.3, olive 2.2. The tests require 2 to 8, the range [T1] gives for temperate broadleaf and needleleaf forests (the earlier 1 to 10 was wider than the source, and the olive's 1.6 was outside it).

## Species forms

- Pine (third round, after the judge found the second a broadleaf crown on a smooth tan trunk). The Scots pine is uninodal: it lays down one whorl of branches a year at the top of the leader, so its branches leave the trunk in tiers; it sheds its shaded lower branches, so an old tree stands on a long clear bole; its branches stand out level or droop a little and turn up at the tips; its crown flattens and goes irregular with age; it keeps its needles two to four years, so only the outer part of each shoot is green and the needles gather in tufts at the branch ends, with bare orange limbs between; and its bark is thick, grey-brown and deeply furrowed low down and thin, flaking and orange-red on the upper trunk and limbs (the reference photo and its bark close-up, observed). The preset follows each of these: `whorl` 4 on a trunk clear for 9.5 of 17 m; `down_angle` 98° at the lowest whorl to 55° at the top (`down_angle_top`, new) with `curve` −12 and `curve_back` 32, so the limbs dip and rise at the tips; a tend-flame envelope, so the longest limbs sit high and the top is flat and broad rather than a cone; side branches in flat sprays (`rotate_offset` 90, new); clusters only on the last 0.5 m of each shoot (`reach`, new); needle brushes (`brush`, new), each a card along the twig cut into a shoot of 24 needles a side at two crossing slopes with seeded lengths, three cards turned 60° about the twig, dark blue-green; and the `bark` preset's upper bark (new), grey-brown furrowed plates turning between 6.5 and 9.5 m into orange-red flakes with a fifth of the furrow depth. The bark is Blendworks' own procedural `bark`, no scan.
- Conifer habit. `growth.habit` (`docs/DESIGN.md`, Tree skeletons) measures it; seeds 1, 2 and 3 of the pine:

| | whorled_share | level_share | branch_angle | clear_bole | whorl_spacing |
|---|---|---|---|---|---|
| `pine`, seeds 1, 2, 3 | 0.92, 0.96, 0.83 | 0.96, 0.87, 0.71 | 85°, 79°, 80° | 0.53, 0.53, 0.48 | 1.02, 0.97, 1.30 m |
| the second round's pine, seed 1 | 1.0 | 0.58 | 67° | 0.24 | 0.97 m |
| oak, birch, maple, olive, willow, seed 1 | 0 | 0.64, 0.22, 0.41, 0.45, 0.14 | 75°, 57°, 58°, 55°, 37° | 0.22 to 0.24 | |

`conifer` asks for `whorled_share ≥ 0.7`, `level_share ≥ 0.6` and `clear_bole ≥ 0.35`, between the pine and the rest: the broadleaves have no whorls, and the second round's pine, whorled but with rising branches down to a fifth of its height, fails on both other marks. The bridge test `test_tree_habit.py` grows the pine with no whorls, with branches down to 3.2 m and with rising branches, and each falls back below the marks.
- Willow (third round, after the judge found it narrow with bare limbs). The in-leaf reference is taller than it is wide, a dome of strands from the top down to near the ground all round. The `willow` preset now grows its own form from `weeping_willow`: 13 m, fourteen limbs that leave the trunk steeply low down (24°) and wider higher up (55°, `down_angle_top`) under a tend-flame envelope, arching (`curve` −35) into a crown 20 m across, and sixty-four thin strands per limb (`tip_radius` 0.018) up to 1.4 times its length, cut at the hem; clusters on the limbs as well (`orders` 3), with flat leaves (`detail` low) so twice as many fit in the vertex cap.
- Birch: clusters along every shoot up to 7 cm in radius (`bearing_radius`), so no bare sticks leave the crown; `lenticels` 1 draws black dashes across the grain in place of vertical fissures.
- Oak and maple were thinned a little (inner_keep 0.2, fewer leaves) to sit inside the foliage band.
