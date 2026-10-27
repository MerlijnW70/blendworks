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
    examples: ["wood, brass, worn metal, stone or marble look", "aged metal with patina", "rust and dirt"],
    steps: ["blender_material_procedural", "blender_material_layer", "blender_assign_material"],
    note: "blender_material_procedural has wood, brass, worn metal, stone, marble and more; blender_material_layer adds wear and dirt through a mask. Scratches run around an axis (around_z, or around with scratch_axis) as on turned parts, along UV u or v (v follows sweep rings, u follows lathes), or along an axis for flat stock. Marble finish polished stays optically flat; honed and rough add relief. Edge and cavity masks follow bevels and creases.",
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
    steps: ["blender_heightfield", "blender_material_procedural"],
    note: "blender_heightfield samples one noise field at world metres, so tile [1, 0] continues tile [0, 0] with no seam: give every tile the same seed and noise settings and a different tile. Keep the finest octave at least two vertex spacings long. skirt true closes a tile into a solid; attributes slope, height and curvature are kept for masks. Roughen a rock or a cliff with blender_noise_displace.",
  },
  {
    id: "rock-set",
    goal: "Rock set",
    examples: ["boulders", "stones", "scatter rocks", "cliff pieces"],
    steps: ["blender_add_primitive", "blender_noise_displace", "blender_displace_noise", "blender_shade_flat", "blender_material_procedural", "blender_instances", "blender_uv_smart_project", "blender_bake", "blender_generate_lods", "blender_export"],
    note: "Start from an ico sphere, shape it with blender_noise_displace (fractal noise in metres: billow for lumps, worley ridged for cracks), add seeded dents or jitter with blender_displace_noise, give it the stone preset, and place variants with blender_instances at points; realize true merges them for export.",
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
