# Ground cover: sources and measurements

Job `ground-cover`. The contract is the "Ground cover" section of `docs/DESIGN.md`; this page lists what it is built on and what was measured.

## Why

A showcase meadow built with Blendworks commands only (trees, scattered rocks, a scanned ground texture, an HDRI sky) still read as CG. Its ground was a displaced plane with an image texture: at eye level a real meadow is a volume of thousands of blades, tufts, flowers and bits of litter at many scales, which hide the soil, cast small shadows on it and break up the horizon line. Before and after renders of that scene are delivered with the job.

## Sources

| Id | Source | Used for |
|---|---|---|
| G1 | M. Thomas, "A generalization of Poisson's binomial limit for use in ecology", Biometrika 36 (1949) 18-25 | Clumped populations: parents as a Poisson process, a Poisson number of children at Gaussian offsets (the Thomas cluster process) |
| G2 | P. A. W. Lewis, G. S. Shedler, "Simulation of nonhomogeneous Poisson processes by thinning", Naval Research Logistics Quarterly 26 (1979) 403-413 | Density times falloff times masks: draw at a bound, keep with the ratio |
| G3 | G. Turk, "Generating random points in triangles", Graphics Gems (1990) 24-28 | Uniform points in a triangle (`sqrt` of the first draw), as in `scatter` |
| G4 | D. G. Horvitz, D. J. Thompson, "A generalization of sampling without replacement from a finite universe", J. Amer. Statist. Assoc. 47 (1952) 663-685 | The contact attribute: each kept element counts its footprint divided by its chance of being kept |
| G5 | H. Vogel, "A better way to construct the sunflower head", Mathematical Biosciences 44 (1979) 179-189, and S1, S31 in `natural-shapes.md` | Petals at the golden angle |
| G6 | T. Sousa, "Vegetation Procedural Animation and Shading in Crysis", GPU Gems 3, chapter 16 (2007) | The wind colours: edge flutter, phase and main bend weights in the vertex colour channels |
| G7 | K. Pelzer, "Rendering Countless Blades of Waving Grass", GPU Gems, chapter 7 (2004) | Crossed alpha cards for grass, many blades per card, and their cost against blade geometry |
| G8 | O. Deussen, P. Hanrahan, B. Lintermann, R. Měch, M. Pharr, P. Prusinkiewicz, "Realistic modeling and rendering of plant ecosystems", SIGGRAPH 1998 | Plant populations as layers of instanced elements, with a few prototypes standing for millions of plants |
| G9 | Khronos, `EXT_mesh_gpu_instancing`: https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Vendor/EXT_mesh_gpu_instancing | The instanced export: TRANSLATION, ROTATION and SCALE accessors on a node with a mesh |
| G10 | Blender Manual, Instance on Points and Collection Info nodes: https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/instances/instance_on_points.html | Instances that share the element meshes, picked per point |
| G11 | Poly Haven, "Sunset Meadow Path" HDRI, CC0: https://polyhaven.com/a/sunset_meadow_path | Colour reference for meadow grass, green and dry (measured below) |
| G12 | Poly Haven, "Forrest Ground 01" texture, CC0: https://polyhaven.com/a/forrest_ground_01 | Reference for leaf litter, twigs and pebbles on a forest floor |

## Measurements

**Reference colours (G11).** Linear RGB of the 4k HDRI below the horizon (rows at 25 % to 45 % of the image height, 1.68 million pixels): 10 % of them are green (G above 1.05 R and 1.2 B), median `[0.094, 0.104, 0.032]`, chromaticity `[0.90, 1, 0.31]` relative to green; 89 % are dry grass (R at least 0.95 G, G above 1.3 B), median `[0.148, 0.124, 0.059]`, chromaticity `[1.19, 1, 0.47]`. The sun is low and warm, which pushes both towards red; the presets keep a cooler and deeper green (`grass` `[0.05, 0.125, 0.018]`, root 0.45 times darker, tip yellower: gains 2.1, 1.65 and 1.0; the first close-up with `[0.075, 0.15, 0.035]` read washed out under the tone mapping) for midday light and a dry colour `[0.36, 0.29, 0.13]` close to the dry chromaticity, and `dry_tips` sets how much of a meadow is dry (20 % of the blades by default, 20 % and 40 % for the short and tall grass of `meadow`, 85 % in `dry_steppe`).

**Instancing cost.** The example meadow (`docs/examples/meadow_cover.py`, a 40 m tile, the `meadow` preset, a camera falloff from 10 m) places 94 785 instances of 60 element meshes, 7.5 million triangles when realized, in 8.7 s. Writing them to a glb with Blender's geometry-node instance export took 119 s; exporting the 60 element meshes and writing the instancing accessors directly takes under a second for the same file.

**Cards.** Crossed cards with thin cut-out blades let a grazing ray pass dozens of transparent surfaces; with Cycles' default of 8 transparent bounces the far field rendered black. Wider blades on cards (at least 45 % of a column at the root) render it with more bounces.

**Dark patches around rocks and trunks.** The first proof renders showed near-black, sharply bounded patches beside the rocks and under the trees. Re-rendering a crop of the hero view from the saved scene isolated the cause: with the contact darkening switched off the patches stayed; with 256 transparent bounces instead of 128 they disappeared at the same render time. They were rays into the openings the masks leave around obstacles, running out of transparent bounces in the surrounding cards. The command now sets at least 512. The openings themselves now fade in over `avoid_falloff` (0.3 m) instead of a hard edge, the meadow, forest floor and steppe presets put tufts and pebbles at the base of obstacles (`hug`), and the darkening is a bounded multiplier.

**Darkening calibration (G12).** Linear luminance of the 2k diffuse map of Forrest Ground 01 (sRGB decoded): percentiles 5, 10, 25, 50, 75, 90 are 0.130, 0.154, 0.192, 0.239, 0.298, 0.366. The 10th over the 50th is 0.64 and the 25th over the 50th 0.80: sheltered soil between the litter is at most about a third darker than open soil. `darken` is therefore at most 0.36, so the multiplier `1 - darken * cover` never falls below 0.64, and the default 0.2 gives 0.80 under full cover.

**Close-up review.** The eye-level close-up of the first delivery read as CG: foreground blades were flat ribbons of near-constant width (`1 - taper s^2` stays above 0.8 over the lower half), straight, pale, and the flowers (1.2 cm petals below the tall grass) and litter were invisible. The blade width now falls as `s^1.15` and the bend as `s^1.7` scaled by height, blades carry a lighter midrib and a V-shaped bump, colours are deeper, flowers are larger and stand above the sward, and the meadow adds thatch (flopped dead grass), dead leaves and twigs over open ground. Compared with CC0/CC BY photographs of wildflower meadows from Wikimedia Commons (warm, mixed green and straw stems, sparse flowers), the render now has the same mix of tapering curved blades, straw stems and scattered flowers; it is still cooler than the photographs under the sunset HDRI.
