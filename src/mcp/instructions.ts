import { CALL_TOOL, SEARCH_TOOL } from "./routing/names.js";
import { WORKFLOWS } from "./routing/workflows.js";

export const UPFRONT_TEXT_LIMIT = 4096;
export const DEFERRED_TEXT_LIMIT = 16_384;

export function serverInstructions(workspace: string): string {
  return [
    "Build 3D assets in Blender with the blender_ tools.",
    `- Every file path is inside the workspace ${workspace}; give paths relative to it.`,
    "- Work in metres; angles are in degrees.",
    `- Many clients list only the core tools. Find any other with ${SEARCH_TOOL}: a query ("round the edges") returns the best tools with their schemas and an example call; a goal returns a workflow's tool sequence and notes. Call a found tool by name, or through ${CALL_TOOL} with tool and arguments; both check the arguments against its schema.`,
    `- Goals ${SEARCH_TOOL} knows: ${WORKFLOWS.map((workflow) => workflow.goal.toLowerCase()).join("; ")}.`,
    "- Check with blender_render_preview often: focus for close-ups; shading clay, wireframe, normals, uv_checker or material_id; views include bottom; format jpeg is smaller.",
    "- blender_scene_info verifies object, vertex and triangle counts and sizes: 100 objects per page (offset, limit), a names glob (\"Bolt*\"), or detail summary. It lists parents, collections and checkpoints.",
    "- Texture in order: model, UV, materials, bake, export.",
    "  - UV: blender_uv_smart_project or blender_uv_unwrap; min_island_area for parts with many notches; blender_uv_pack with target coverage for one shared atlas.",
    "  - Materials: blender_material_procedural (wood, brass, worn metal, stone, marble and more), blender_material_layer for wear and dirt; scratches run around an axis (brass default around_z), along UV u or v, or along an axis; brass age new, handled, aged or dull darkens engraved recesses; marble vein_softness, branching, finish polished (default), honed or rough, presets bark, moss, leaf, soil, sand, grass_ground; layer masks slope, height, up_facing, attribute, joined by with_masks; stone hard_cells, blender_material_pbr from images, blender_material_nodes and blender_material_info for node graphs.",
    "  - Bake: blender_bake with rewire true; atlas_sizes gives small parts smaller images. Export with blender_export, for example to asset.glb.",
    "- Build parts with the shape tools, not by hand: blender_sweep, blender_lathe, blender_loft, blender_extrude_outline, blender_gear, blender_instances (phyllotaxis), blender_boolean with cutters (solver auto), blender_engrave for text on a plane, cylinder, ring or curve, blender_engrave_scale for dial ticks in one cut, and blender_clean_mesh after cuts. Engraving keeps meshes closed and mapped; sweep closed true closes an arc. Use blender_run_python only when no other tool can.",
    "- Natural shapes: blender_noise_displace adds noise in metres; blender_heightfield builds seamless terrain; blender_erode weathers it with masks; blender_shell grows shells; blender_grow_tree (weeping, gnarled, wind-bent presets) and blender_lsystem grow plants, blender_tree_mesh, blender_tree_leaves add bark, leaves; rocks: blender_fracture, blender_chip, blender_abrade.",
    "- Scatter: blender_scatter places copies over a surface with Poisson disk spacing in metres, slope, height or attribute masks, power-law sizes, alignment and an embed on slopes; build each piece with its base at the origin (blender_set_origin bottom_centre).",
    "- Structure a scene with blender_add_empty, blender_parent, blender_collection_create and blender_collection_link.",
    "- Save a blender_checkpoint before risky steps. The headless session autosaves; after a crash, timeout or cancel it restarts and names the restored state. Every tool takes timeout_seconds.",
  ].join("\n");
}
