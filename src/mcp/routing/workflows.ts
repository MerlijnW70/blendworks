export interface Workflow {
  id: string;
  goal: string;
  examples: string[];
  steps: string[];
  note: string;
  headline?: boolean;
}

export const WORKFLOWS: Workflow[] = [
  {
    id: "texturing",
    headline: true,
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
    note: "blender_material_procedural has wood, brass, worn metal, stone, marble and more; blender_material_layer adds wear and dirt through a mask. Scratches run around an axis (around_z, or around with scratch_axis) as on turned parts, along UV u or v (v follows sweep rings, u follows lathes), or along an axis for flat stock. The brass age new, handled, aged or dull darkens the recesses. Marble vein_softness and branching shape the veins; finish polished stays optically flat, honed and rough add relief. Edge and cavity masks follow bevels and creases. Natural looks: bark, moss, leaf, soil, sand and grass_ground presets, and layer masks slope (angle_min, angle_max), height (z_min, z_max), up_facing (moss or snow on top) and attribute (slope, height or curvature from heightfield), combined with with_masks; stone patches are soft unless hard_cells is set.",
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
    headline: true,
    goal: "Engraved brass dial",
    examples: ["engraved brass ring", "clock face with numbers", "dial with a scale", "astrolabe or armillary ring"],
    steps: ["blender_lathe", "blender_engrave", "blender_clean_mesh", "blender_material_procedural", "blender_material_layer", "blender_uv_smart_project", "blender_bake", "blender_export"],
    note: "Text, numbers and zodiac or planet symbols ({aries}, {sun}) go into a surface with blender_engrave: a plane, a face region, a cylinder band or a curve. repeat makes a scale, for example a number every 10 degrees, and blender_engrave_scale cuts all the tick marks of a dial in one cut on a flat ring or a cylinder band. Engraving keeps meshes closed and UV-mapped. Brass ageing comes from blender_material_procedural brass and a cavity layer.",
  },
  {
    id: "terrain-tiles",
    headline: true,
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
    headline: true,
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
    note: "blender_sweep a circle or rectangle preset along waypoints, with fillet_radius for smooth bends. Rings, arcs and springs: the circle, arc and helix paths, exact and without a seam; closed true closes an arc into a ring.",
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
    note: "blender_extrude_outline takes holes directly. Cut many holes at once with blender_boolean cutters and manifold true (solver auto picks the solver and reports why); it cleans the result, and blender_clean_mesh does the same to any mesh.",
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
    headline: true,
    goal: "Tree with leaves",
    examples: ["oak with roots and leaves", "spruce with needles", "game tree with a triangle budget", "weeping willow or wind-bent coastal tree", "photoreal birch, pine, maple or olive"],
    steps: ["blender_grow_tree", "blender_tree_mesh", "blender_tree_leaves", "blender_material_procedural"],
    note: "blender_grow_tree grows the skeleton; a species preset (oak, birch, pine, willow, maple, olive) also sets the bark, leaves and twigs of the next two steps, and weeping_willow, gnarled_oak or windswept_coastal give a form; and gravitropism and phototropism (by order and thinness), stiffness (sag), wind, gnarl, twist, kink_probability and, for levels, curve_back and curve_variation shape any tree. blender_tree_mesh turns it into one closed bark mesh (junction skin or voxel, flare, root_flare, bark_noise, lod for a triangle budget, min_radius drops twigs) with UVs in metres and the slots bark, fresh_wood and roots; blender_tree_leaves puts leaf clusters on fine twigs beyond the tips with per-leaf size, colour, age, damage, curl and shape (measure reports the crown fill). Then material_procedural bark with coordinates uv and grain y, leaf with cutout, and export: the skeleton rides along in the glTF extras.",
  },
  {
    id: "character",
    headline: true,
    goal: "Characters",
    examples: ["walking humanoid for a game", "four-legged animal that trots", "chest whose lid opens", "skinned mesh with clips"],
    steps: ["blender_rig_template", "blender_skin_bind", "blender_animation_preset", "blender_clip_pose", "blender_render_preview", "blender_export"],
    note: "Model the parts facing -Y with their feet at z 0, then blender_rig_template humanoid, quadruped, hinge, piston or wheel fitted to the meshes, with landmarks such as left_knee where the joints are; its bone_map goes into the judge spec's boneMap. blender_skin_bind binds with automatic weights, at most 4 per vertex, normalised; bones limits a mesh to some bones, rigid gives a head, hand or lid to one bone. blender_animation_preset walk, trot or idle loops by construction (root_motion moves the Root bone); props open, spin, turn or pump. blender_clip_keys keys your own poses and shape keys, blender_ik_chain and blender_bone_constraint pose limbs and are baked on export. Check frames with blender_clip_pose and blender_render_preview, then blender_export a .glb: every clip becomes a named animation, and the judge checks rig, skin and animation.",
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
    id: "photographic-look",
    goal: "Photographic final render",
    examples: ["photoreal hero shot", "golden hour render with depth of field", "final render with haze", "beauty shot at full resolution"],
    steps: ["blender_set_world_hdri", "blender_add_camera", "blender_camera_setup", "blender_atmosphere", "blender_render_preview", "blender_render_final"],
    note: "Light with an HDRI, place a camera, then blender_camera_setup: focal_length, fstop with focus_object on the subject for depth of field, physical exposure (shutter, iso; exposure = reference_ev - EV100) or exposure in stops, and an AgX look such as base_contrast or punchy. blender_atmosphere adds haze by visibility in metres (contrast falls to 2 % there), height_falloff and ground_fog; previews show it as cheap depth haze. Check with blender_render_preview, then blender_render_final writes up to 4096 px with adaptive sampling, denoising and a time_limit, plus depth, normal, albedo and object_id passes, and motion_blur for animation.",
  },
  {
    id: "sky-weather",
    goal: "Sky and weather for an outdoor scene",
    examples: ["sunny day with cumulus", "overcast or rainy day", "thunderstorm with lightning", "golden hour or dusk sky"],
    steps: ["blender_weather", "blender_sky", "blender_clouds", "blender_render_preview", "blender_render_final"],
    note: "blender_weather does it in one call: preset clear, hazy, fair_cumulus, scattered, broken, overcast, light_rain, heavy_rain or thunderstorm (golden_hour, clear_golden_hour, dusk, scattered_dusk, stormy_golden_hour), or storm 0-1, with time_of_day or sun, seed and overrides for dust, visibility, rain, wet, lightning. It builds the procedural sky (blender_sky: sun by elevation and azimuth or date, time, latitude and longitude, a matching sun lamp and exposure), the clouds (blender_clouds: genus, coverage, base, thickness, density, wind, seed), rain veils and streaks, wet ground, a lightning bolt and haze. Clouds form auto shows a cheap sheet in previews and EEVEE and volumes in blender_render_final.",
  },
  {
    id: "liquids",
    goal: "Water and other liquids",
    examples: ["a lake with a river flowing into it", "ocean waves on a beach", "a glass of red wine", "spilled coffee on a table"],
    steps: ["blender_weather", "blender_liquid_body", "blender_liquid_fill", "blender_shore_stones", "blender_material_liquid", "blender_ground_cover", "blender_render_final"],
    note: "Set blender_weather first: water takes its wind (ripples and waves follow it) and sky. blender_liquid_body kind lake or pond fills the hollow at point to just below its spill level (or level, depth), river follows path or runs from point down the terrain's lowest line (width, depth, carve, Manning roughness; it joins a lake it reaches), ocean takes wind and fetch (JONSWAP and Pierson-Moskowitz wave heights, whitecaps, beach), puddle fills a hollow of a surface; the ground and rocks at the shore get liquid_depth and liquid_wet and darken as wet ground. blender_liquid_fill fills any container (lathe a glass, extrude a tank) by level, volume in litres or fill share, with meniscus, tilt, a 0.1 mm gap to the wall, glass true for the container, foam and bubbles for beer, drips, a pour stream and a spill of a given area. Presets: water_fresh, water_sea, water_muddy, wine, wine_white, beer, oil, milk, juice, juice_grapefruit, coffee, paint, honey (extra light amber), honey_water_white, honey_extra_white, honey_white, honey_extra_light_amber, honey_light_amber, honey_amber, honey_dark_amber (the USDA colour classes), syrup, mud, lava, molten_metal. blender_shore_stones lays clustered, partly buried stones along the water line, angular to round by how close the water is. blender_ground_cover and blender_scatter keep out of the water (liquid avoid by default, shore for reeds); blender_render_final turns caustics off for clean glass and water.",
  },
  {
    id: "review",
    goal: "Check and deliver",
    examples: ["look at the model", "verify counts", "export the asset"],
    steps: ["blender_render_preview", "blender_scene_info", "blender_uv_info", "blender_export"],
    note: "Look often: blender_render_preview focus gives close-ups, shading clay, wireframe, normals, uv_checker or material_id shows form, seams and slots, views include bottom, and format jpeg is smaller. blender_scene_info checks counts and sizes 100 objects per page (offset, limit), with a names glob (\"Bolt*\") or detail summary, and lists parents, collections and checkpoints. Export the final asset with blender_export, for example to asset.glb; its defaults pass the glTF validator.",
  },
  {
    id: "ground-cover",
    goal: "Grass, flowers and litter on terrain",
    examples: ["meadow", "lawn", "forest floor", "dry steppe", "grass on the ground"],
    steps: ["blender_heightfield", "blender_add_camera", "blender_ground_cover", "blender_render_preview", "blender_ground_cover_export"],
    note: "Make the terrain and the camera first, then one blender_ground_cover call with a preset (meadow, forest_floor, dry_steppe, lawn) or populations: density is elements per square metre, clumping gathers them, slope, height_range, attribute (erosion, deposition), noise and distance masks thin them, avoid keeps them clear of the obstacles (trunks, rocks) with a soft avoid_falloff, hug gathers tufts at their base, and under puts litter beneath the trees. camera (or cameras, one per shot) with near keeps full density up to near metres and (near / distance)^2 beyond, view_only drops what the camera cannot see, and budget caps the instances: the near distance shrinks until they fit. form auto uses real blades near and alpha cards beyond card_distance. The ground gets a cover_density attribute and its materials darken by at most a third under dense cover. blender_ground_element builds one element for blender_scatter or blender_instances. Export with blender_ground_cover_export: instances (EXT_mesh_gpu_instancing) or realized LODs; wind true writes the wind colours as COLOR_0.",
  },
];

export const GOAL_LIST = "list";

export function headlineGoals(): string[] {
  return WORKFLOWS.filter((workflow) => workflow.headline === true).map((workflow) => workflow.goal.toLowerCase());
}

export function workflowTools(): string[] {
  return [...new Set(WORKFLOWS.flatMap((workflow) => workflow.steps))];
}
