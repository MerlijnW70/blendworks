export interface Workflow {
  id: string;
  goal: string;
  examples: string[];
  steps: string[];
  note: string;
}

export const WORKFLOWS: Workflow[] = [
  {
    id: "texturing",
    goal: "Texture an asset",
    examples: ["texture a prop", "game-ready textures", "materials and bake", "textured crate"],
    steps: ["blender_uv_smart_project", "blender_uv_pack", "blender_material_procedural", "blender_material_layer", "blender_bake", "blender_image_save", "blender_export"],
    note: "Model, then UV, then materials, then bake, then export. Use blender_uv_unwrap when seams are marked; on parts with many notches, use min_island_area on blender_uv_smart_project and target coverage on blender_uv_pack. Bake with rewire true so the asset carries image textures; atlas_sizes gives small parts smaller images, and the result reports the GPU memory.",
  },
  {
    id: "materials",
    goal: "Realistic materials",
    examples: ["wood, brass, worn metal, stone or marble look", "aged metal with patina", "rust and dirt", "bark, moss, soil, sand or leaf", "moss on up-facing slopes"],
    steps: ["blender_material_procedural", "blender_material_layer", "blender_assign_material"],
    note: "blender_material_procedural has wood, brass, worn metal, stone, marble and more; blender_material_layer adds wear and dirt through a mask. Scratches run around an axis (around_z, or around with scratch_axis) as on turned parts, along UV u or v (v follows sweep rings, u follows lathes), or along an axis for flat stock. Marble finish polished stays optically flat; honed and rough add relief. Edge and cavity masks follow bevels and creases. Natural looks: bark, moss, leaf, soil, sand and grass_ground presets, and layer masks slope (angle_min, angle_max), height (z_min, z_max), up_facing (moss or snow on top) and attribute (slope, height or curvature from heightfield), combined with with_masks; stone patches are soft unless hard_cells is set.",
  },
  {
    id: "node-material",
    goal: "Custom shader from nodes",
    examples: ["node graph material", "edit a material's nodes"],
    steps: ["blender_material_info", "blender_material_nodes", "blender_assign_material"],
    note: "blender_material_nodes builds any other look from a node graph of allow-listed nodes (no script nodes); blender_material_info reads a material's graph back in the same format to edit it. Both work with layers, bake and export.",
  },
  {
    id: "pbr-images",
    goal: "PBR material from image files",
    examples: ["albedo, normal and roughness maps", "material from my textures"],
    steps: ["blender_image_load", "blender_material_pbr", "blender_assign_material"],
    note: "Load each map from the workspace with its colour space, then build the material from the maps.",
  },
  {
    id: "engraved-dial",
    goal: "Engraved brass dial",
    examples: ["engraved brass ring", "clock face with numbers", "dial with a scale", "astrolabe or armillary ring"],
    steps: ["blender_lathe", "blender_engrave", "blender_clean_mesh", "blender_material_procedural", "blender_material_layer", "blender_uv_smart_project", "blender_bake", "blender_export"],
    note: "Text, numbers and zodiac or planet symbols ({aries}, {sun}) go into a surface with blender_engrave: a plane, a face region, a cylinder band or a curve. repeat makes a scale, for example a number every 10 degrees. Brass ageing comes from blender_material_procedural brass and a cavity layer.",
  },
  {
    id: "terrain-tiles",
    goal: "Terrain tiles",
    examples: ["landscape", "mountains", "heightmap ground", "terrain with ridges", "tiles that join"],
    steps: ["blender_heightfield", "blender_erode", "blender_material_nodes", "blender_material_procedural"],
    note: "blender_heightfield samples one noise field at world metres, so tile [1, 0] continues tile [0, 0] with no seam: give every tile the same seed and noise settings and a different tile. Keep the finest octave at least two vertex spacings long. skirt true closes a tile into a solid; attributes slope, height and curvature are kept for masks. Roughen a rock or a cliff with blender_noise_displace. Erode after building the tiles: pass the neighbouring tiles as names so they are eroded as one grid and still share their edge heights (one tile alone keeps its edges fixed). mode both alternates droplets and thermal talus sweeps; blender_erode writes erosion and deposition (metres) beside slope, and a blender_material_nodes attribute node reads them as masks. Lague's defaults are strong on metre terrain: lower capacity and erode_rate and use many droplets.",
  },
  {
    id: "scatter-terrain",
    goal: "Scatter rocks or plants over terrain",
    examples: ["scatter rocks on terrain", "rubble on a slope", "plants on the ground", "trees over a hillside", "pebbles with natural spacing"],
    steps: ["blender_heightfield", "blender_noise_displace", "blender_set_origin", "blender_scatter", "blender_material_procedural"],
    note: "Model each piece with its base at the origin (blender_set_origin to bottom_centre), then blender_scatter over the terrain: min_distance is the spacing of the smallest pieces in metres, measured in 3D so it holds on slopes; density_mask slope with slope_range keeps pieces off steep faces, or attribute with the slope or height that blender_heightfield writes. scale_distribution power with the default exponent -2 gives many small stones and a few large ones, and larger pieces keep proportionally more room. embed 0.2 sinks each piece so it does not float on a slope; align blend leans it with the ground. sources takes several pieces with weights; the same seed gives the same layout. blender_instances stays for points you choose yourself.",
  },
  {
    id: "shell",
    goal: "Seashell, snail or ammonite",
    examples: ["conch", "snail shell", "ammonite", "nautilus", "spiral shell"],
    steps: ["blender_shell", "blender_set_origin", "blender_material_procedural", "blender_render_preview"],
    note: "blender_shell grows a generating curve along a logarithmic spiral. W is the growth per whorl (1.3 to 1.5 for a spire, about 2 for an ammonite), D the distance of the curve from the axis (small for a snail, 0.5 for a coil), T the drop per whorl (0 gives a flat coil, 1 or more a spire), size the aperture in metres, ribs across the growth and spiral_ridges along it, lip a flared rim, thickness a hollow wall that opens at the aperture, handedness right or left. The shell winds downwards from an apex on top; keep D times W above 1 when T is 0, or the whorls overlap. Its UVs are in metres, so a stone or marble preset keeps its scale to the aperture.",
  },
  {
    id: "rock-set",
    goal: "Rock set",
    examples: ["boulders", "stones", "scatter rocks", "cliff pieces", "fractured or chipped rocks", "worn pebbles"],
    steps: ["blender_add_primitive", "blender_fracture", "blender_chip", "blender_abrade", "blender_noise_displace", "blender_shade_smooth", "blender_material_procedural", "blender_instances", "blender_uv_smart_project", "blender_bake", "blender_generate_lods", "blender_export"],
    note: "Start from a convex block (a cube, or an ico sphere with subdivisions 3 or 4 scaled to size; blender_blob for an organic base, then blender_remesh). Fresh, blocky rocks: blender_fracture (binary gives about 6 faces and 8 vertices per piece, voronoi cells) then blender_chip, with a fresh_material for the cut faces. Worn rocks: keep one piece, blender_chip, then blender_abrade (edges round, large faces stay; amount up to 1), then blender_noise_displace in metres for grain (a lump layer near 4 % of the rock, ridged worley cracks near 1 %, fine fBm near 0.5 %), then shade smooth. blender_displace_noise only adds jitter or dents. Fracture and chip need a closed convex solid, so run them before any displacement; blender_remesh joins shells after a boolean. Give the stone preset, place variants with blender_instances at points; realize true merges them for export.",
  },
  {
    id: "pipes",
    goal: "Pipes, rails, cables and springs",
    examples: ["pipe along a path", "cable", "railing", "coil spring", "ring or frame"],
    steps: ["blender_sweep", "blender_material_procedural"],
    note: "blender_sweep a circle or rectangle preset along waypoints, with fillet_radius for smooth bends. Rings, arcs and springs: the circle, arc and helix paths, exact and without a seam.",
  },
  {
    id: "turned-parts",
    goal: "Turned parts",
    examples: ["bottle", "flange", "handle", "vase", "knob", "candlestick"],
    steps: ["blender_lathe", "blender_loft", "blender_shade_smooth"],
    note: "blender_lathe a profile of [x, z] points that starts and ends on the axis; blender_loft for sections that change shape.",
  },
  {
    id: "plates",
    goal: "Plates, brackets and signs with holes",
    examples: ["bracket", "sign", "plate with bolt holes", "cut many holes"],
    steps: ["blender_extrude_outline", "blender_boolean", "blender_clean_mesh", "blender_bevel"],
    note: "blender_extrude_outline takes holes directly. Cut many holes at once with blender_boolean cutters and manifold true; it cleans the result, and blender_clean_mesh does the same to any mesh.",
  },
  {
    id: "gear-train",
    goal: "Gear train and chain drive",
    examples: ["gears", "sprockets and chain", "bike drive"],
    steps: ["blender_gear", "blender_sprocket", "blender_roller_chain"],
    note: "blender_gear, blender_sprocket and blender_roller_chain build gear trains; pair a sprocket with its chain pitch.",
  },
  {
    id: "fasteners",
    goal: "Bolts and rivets",
    examples: ["rivets along a seam", "bolt circle", "row of bolts"],
    steps: ["blender_lathe", "blender_instances", "blender_rivet_line"],
    note: "Build one bolt with blender_lathe, then blender_instances (on a circle, along a curve or at points) or blender_rivet_line; realize true merges them for export.",
  },
  {
    id: "phyllotaxis",
    goal: "Sunflowers, pine cones and rosettes",
    examples: ["sunflower head with seeds and petals", "pine cone with overlapping scales", "succulent rosette of leaves", "organs in the golden angle"],
    steps: ["blender_mesh_from_data", "blender_instances", "blender_material_procedural"],
    note: "Build one seed, petal, scale or leaf with its base at the origin and its length along X (blender_mesh_from_data with UVs), then blender_instances with phyllotaxis: mode disc (c metres, organ n at radius c*sqrt(n)), cone (radius, height), sphere (radius, polar_extent) or surface (a mesh of revolution), golden true for the exact angle 137.5078 degrees, scale_by_age and tilt_by_age with a curve, jitter with a seed. Organs sit on the surface normal with X pointing away from the centre; start gives a ring of petals around a disc of seeds.",
  },
  {
    id: "lsystem-plant",
    goal: "L-system plants",
    examples: ["fern or compound leaf", "herb or flowering bush from a grammar", "stochastic plants of one species", "parametric L-system tree", "branching plant with leaves and flowers"],
    steps: ["blender_lsystem", "blender_assign_material", "blender_material_procedural"],
    note: "Build one leaf or flower with its base at the origin and its length along X (blender_mesh_from_data), then blender_lsystem with a preset from the book (bracketed_1_24a to f, bush_1_25, stochastic_1_27, monopodial_2_6a, ternary_2_8a, compound_leaf_5_11b) or your own axiom and rules such as F -> F[+F]F[-F]F; parametric modules F(l) and conditions as in A(x) : x > 3 -> B(x*2); a probability after a rule (: 0.5) makes it stochastic, and the seed picks the specimen. Turtle: F draws, + - turn, & ^ pitch, \ / roll, [ ] branch, ! thins, ' picks the next organ variant. organs places a mesh at each occurrence of a letter (apices stay in the string, so A or X can carry a flower) in the turtle's frame, heading along X. The plant is a skeleton for tree meshing; max_length and max_nodes refuse a grammar that grows too big before it runs.",
  },
  {
    id: "tree",
    goal: "Tree with leaves",
    examples: ["oak with roots and leaves", "spruce with needles", "game tree with a triangle budget"],
    steps: ["blender_grow_tree", "blender_tree_mesh", "blender_tree_leaves", "blender_material_procedural"],
    note: "blender_grow_tree grows the skeleton; blender_tree_mesh turns it into one closed bark mesh (junction skin or voxel, flare, root_flare, bark_noise, lod for a triangle budget, min_radius drops twigs) with UVs in metres and the slots bark, fresh_wood and roots; blender_tree_leaves puts leaf cards (or a needle cluster as source) on the twig tips and outer orders. Then material_procedural bark with coordinates uv and grain y, leaf with cutout, and export: the skeleton rides along in the glTF extras.",
  },
  {
    id: "surface-detail",
    goal: "Wear and face edits",
    examples: ["dents", "battle damage", "taper faces", "find faces"],
    steps: ["blender_mesh_query", "blender_transform_selection", "blender_displace_noise"],
    note: "Find faces with blender_mesh_query, move them with blender_transform_selection, and add wear with blender_displace_noise.",
  },
  {
    id: "hierarchy",
    goal: "Structure a scene",
    examples: ["group parts", "parent objects", "collections for export"],
    steps: ["blender_add_empty", "blender_parent", "blender_collection_create", "blender_collection_link", "blender_collection_unlink"],
    note: "blender_add_empty makes grouping nodes with a display type and size; blender_scene_info reports parents and collections, and blender_export keeps the empties above exported objects and takes a collection.",
  },
  {
    id: "safe-edit",
    goal: "Risky edit with a way back",
    examples: ["undo point", "try a boolean safely"],
    steps: ["blender_checkpoint", "blender_boolean", "blender_restore_checkpoint"],
    note: "Save a named state with blender_checkpoint before risky steps, and go back with blender_restore_checkpoint; blender_scene_info lists the checkpoints.",
  },
  {
    id: "lods",
    goal: "Levels of detail for a game engine",
    examples: ["LODs", "game-ready package", "lower poly versions"],
    steps: ["blender_generate_lods", "blender_render_preview", "blender_export"],
    note: "blender_generate_lods makes <name>_LOD1 to <name>_LOD<n> by decimation that keeps borders, materials and UV seams, and reports each level's triangles, error and screen error. Give ratios (falling), or max_screen_error in pixels with the distances in metres where each level is used; the source objects are renamed <name>_LOD0. Export every <name>_LOD<n> object to one .glb, then package it: blendworks package asset.glb --out packaged --lods n --ratios ... renders each level against LOD0, compresses with gltfpack, and validates and compares both packages.",
  },
  {
    id: "poly-haven",
    goal: "Lighting, textures or reference from Poly Haven",
    examples: ["free HDRI", "CC0 texture", "reference model"],
    steps: ["library_search", "library_preview", "library_download", "library_apply"],
    note: "Poly Haven's free CC0 assets: HDRIs light the scene, texture sets become PBR materials, and models serve as reference.",
  },
  {
    id: "review",
    goal: "Check and deliver",
    examples: ["look at the model", "verify counts", "export the asset"],
    steps: ["blender_render_preview", "blender_scene_info", "blender_uv_info", "blender_export"],
    note: "Export the final asset with blender_export, for example to asset.glb; its defaults pass the glTF validator.",
  },
];

export function workflowTools(): string[] {
  return [...new Set(WORKFLOWS.flatMap((workflow) => workflow.steps))];
}
