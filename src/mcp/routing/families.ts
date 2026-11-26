export interface FamilyLine {
  family: string;
  priority: number;
  text: string;
}

export const MAX_FAMILY_LINE = 240;

export const FAMILY_LINES: FamilyLine[] = [
  { family: "shapes", priority: 10, text: "Shapes: blender_sweep, blender_lathe, blender_loft, blender_extrude_outline, blender_gear and blender_shell." },
  { family: "materials", priority: 10, text: "Materials: blender_material_procedural presets (wood, brass, stone, marble, bark), blender_material_layer for wear, blender_material_pbr from images, blender_material_nodes and blender_material_info graphs." },
  { family: "uv", priority: 10, text: "UV: blender_uv_smart_project, or blender_uv_unwrap on marked seams; blender_uv_pack packs one shared atlas." },
  { family: "baking", priority: 20, text: "Bake: blender_bake with rewire true gives the asset image textures." },
  { family: "mesh_edit", priority: 20, text: "Edits: blender_boolean with cutters, blender_bevel, blender_shade_smooth, and blender_clean_mesh after cuts." },
  { family: "scene", priority: 20, text: "Scene: blender_new_scene starts empty; blender_scene_info pages big scenes with offset, limit and a names glob." },
  { family: "objects", priority: 30, text: "Objects: blender_add_primitive, blender_transform, blender_set_origin, blender_duplicate and blender_join." },
  { family: "engraving", priority: 30, text: "Engraving: blender_engrave cuts text and symbols into planes, cylinders, rings, curves; blender_engrave_scale cuts dial ticks." },
  { family: "placement", priority: 30, text: "Placement: blender_instances (circle, curve, phyllotaxis), blender_rivet_line, and blender_scatter with natural spacing over terrain." },
  { family: "wear", priority: 40, text: "Terrain, rocks: blender_heightfield, blender_erode, blender_fracture, blender_chip, blender_abrade; blender_noise_displace adds noise." },
  { family: "natural", priority: 40, text: "Plants: blender_grow_tree (weeping, gnarled, wind-bent presets), blender_tree_mesh, blender_tree_leaves and blender_lsystem." },
  { family: "rigging", priority: 40, text: "Characters: blender_rig_template fits a humanoid, quadruped or prop rig; blender_skin_bind weights meshes." },
  { family: "animation", priority: 40, text: "Animation: blender_animation_preset (walk, trot, idle, open, spin), blender_clip_keys for your own." },
  { family: "library", priority: 50, text: "Poly Haven: library_search, then library_apply for an HDRI or a texture material." },
  { family: "hierarchy", priority: 50, text: "Structure: blender_add_empty, blender_parent, blender_collection_create and blender_collection_link." },
  { family: "modifiers", priority: 60, text: "Modifiers: blender_add_modifier (displace, screw, lattice, shrinkwrap and more), blender_remesh." },
  { family: "from_data", priority: 60, text: "Data: blender_mesh_from_data builds meshes with UVs." },
  { family: "lods", priority: 60, text: "Game assets: blender_generate_lods makes levels of detail." },
  { family: "photography", priority: 70, text: "Photo: blender_camera_setup (lens, f-stop focus, exposure, AgX look), blender_atmosphere (haze), blender_render_final to a file." },
  { family: "lighting", priority: 70, text: "Lighting: blender_add_light, blender_add_camera, blender_set_world_hdri." },
  { family: "textures", priority: 70, text: "Images: blender_image_load, blender_image_new, blender_image_save." },
  { family: "faces", priority: 80, text: "Faces: blender_mesh_query finds faces, blender_transform_selection moves them." },
  { family: "files", priority: 80, text: "Files: blender_save_blend, blender_load_blend, blender_import." },
  { family: "weather", priority: 40, text: "Weather: blender_weather, blender_sky, blender_clouds." },
  { family: "ground_cover", priority: 40, text: "Ground cover: blender_ground_cover grows meadows, lawns and forest floors." },
  { family: "liquids", priority: 40, text: "Liquids: blender_liquid_body (ocean, lake, river, puddle), blender_liquid_fill (containers, spills), blender_material_liquid." },
];
