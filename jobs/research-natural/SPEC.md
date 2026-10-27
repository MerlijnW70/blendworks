# Job: Research natural shapes for Blendworks

Blendworks builds hard-surface assets well: crates, tools, machines and instruments. Natural shapes are its weak side: trees, plants, rocks and cliffs, terrain, shells, coral, bark, roots, fruit and organic forms. Research how the state of the art makes natural shapes believable, and turn the findings into a concrete, prioritised plan for Blendworks commands, presets and judge rules.

## Base

- **Base commit:** 16c3ba9. Rebase onto the latest `main` before delivering.

## Required

1. **Survey of methods**, with primary sources (papers, official docs, source code) for each:
   - growth and branching: L-systems, space colonisation, the Weber–Penn model (the Blender Sapling add-on), and tree generators such as SpeedTree, Grove and tree-gen;
   - erosion and weathering: hydraulic and thermal erosion, and rock fracture (Voronoi, boolean shatter);
   - SDFs and implicit surfaces: metaballs, smooth union and remeshing;
   - noise stacks: fBm, domain warping, ridged noise and Worley noise, with parameters that read as natural at real-world scale;
   - phyllotaxis and the golden angle; shells (logarithmic spirals, Raup's model); differential growth; reaction–diffusion;
   - scattering and ecosystems: Poisson disk sampling, density by slope and height, and instancing at scale;
   - Blender specifics: Geometry Nodes, displacement, remesh and voxel workflows, the Sapling and Ivy Gen add-ons, and their licences;
   - photogrammetry and scan libraries (Poly Haven, ambientCG, Quixel and their licences) as a reference or a source.
2. **What makes it read as natural:** measurable properties that separate believable from fake, each with a source:
   - fractal dimension and self-similarity;
   - size distributions;
   - allometry, such as Leonardo's rule for branch area;
   - curvature distributions;
   - silhouette irregularity, with no visible repetition or tiling;
   - material variation.
3. **Gap analysis against Blendworks:** read the bridge commands (`bridge/blendworks_bridge/commands/`), the presets and the judge rules, and list what is missing to build each of these, commands only:
   - a tree with roots;
   - a rock set with erosion;
   - a fern or flower;
   - a shell;
   - a terrain tile with scattering.
4. **Plan:** a prioritised list of new commands, presets and judge rules, each with:
   - its parameters;
   - the algorithm and source it follows;
   - a test that would prove it;
   - an effort estimate;
   - the licence implications. GPL code cannot go into the MIT parts. Name every algorithm's or library's licence.
5. **Judge rules for natural assets:** concrete, measurable rules that the Blender judge could check, with thresholds justified by sources or by measurements on reference assets. Examples are a branch area-ratio check, a repetition detector and silhouette fractal dimension. Say how the visual judge rubric should change for natural assets.

## Deliver

- `docs/research/natural-shapes.md`: the report, in English. Every claim has a source with a URL. Add a "not verified" label where you could not confirm something.
- Optional: small figures in `docs/research/natural-shapes/` (SVG, or PNG renders you made yourself in Blender), each with how it was made.
- No code changes.
- One commit; the patch from `git format-patch -1 --stdout`. Announce its sha256 to the judge.

## Acceptance

1. All five required parts are present, with primary sources.
2. The judge checks at least 10 claims against their sources. All must hold.
3. The plan is specific enough to write the next job specs straight from it.
