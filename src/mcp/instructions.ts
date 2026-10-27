export function serverInstructions(workspace: string): string {
  return [
    "Build 3D assets in Blender with the blender_ tools.",
    "- Work in metres; angles are in degrees.",
    "- Check the result with blender_render_preview after every few steps, and fix what looks wrong.",
    "- Use blender_scene_info to verify object, vertex and triangle counts and sizes.",
    "- Texture in this order: model, then UV, then materials, then bake, then export.",
    "  - UV: blender_uv_smart_project or blender_uv_unwrap, and blender_uv_pack to share one atlas between objects.",
    "  - Materials: blender_material_procedural with blender_material_layer for wear and dirt, or blender_material_pbr from image maps loaded with blender_image_load.",
    "  - Bake: blender_bake with rewire true, so the asset carries image textures; keep baked maps with blender_image_save.",
    "- Export the final asset with blender_export, for example to asset.glb.",
    "- For real lighting, materials or reference, start from Poly Haven's free CC0 assets: library_search, then library_preview, library_download and library_apply. HDRIs light the scene, texture sets become PBR materials, and models serve as reference.",
    `- Every file path is inside the workspace ${workspace}; give paths relative to it.`,
  ].join("\n");
}
