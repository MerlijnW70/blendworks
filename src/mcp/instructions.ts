export function serverInstructions(workspace: string): string {
  return [
    "Build 3D assets in Blender with the blender_ tools.",
    "- Work in metres; angles are in degrees.",
    "- Check the result with blender_render_preview after every few steps, and fix what looks wrong.",
    "- Use blender_scene_info to verify object, vertex and triangle counts and sizes.",
    "- Export the final asset with blender_export, for example to asset.glb.",
    `- Every file path is inside the workspace ${workspace}; give paths relative to it.`,
  ].join("\n");
}
