export const CORE_RANKING: string[] = [
  "blender_assign_material",
  "blender_material_procedural",
  "blender_sweep",
  "blender_export",
  "blender_instances",
  "blender_material_layer",
  "blender_bake",
  "blender_add_primitive",
  "blender_clean_mesh",
  "blender_lathe",
  "blender_uv_pack",
  "blender_boolean",
  "blender_render_preview",
  "blender_uv_smart_project",
  "blender_new_scene",
  "blender_displace_noise",
  "blender_add_material",
  "blender_delete",
  "blender_add_empty",
  "blender_bevel",
  "blender_engrave",
  "blender_add_modifier",
  "blender_scene_info",
  "library_apply",
];

export const CORE_MAX_TOOLS = 12;
export const CORE_BUDGET_BYTES = 40_000;

export function rankCore(sources: Record<string, number>[]): string[] {
  const score = new Map<string, number>();
  for (const source of sources) {
    const total = Object.values(source).reduce((sum, count) => sum + count, 0);
    if (total === 0) continue;
    for (const [name, count] of Object.entries(source)) score.set(name, (score.get(name) ?? 0) + count / total);
  }
  return [...score].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0])).map(([name]) => name);
}

export function chooseCore(ranking: string[], sizes: Map<string, number>, budgetBytes: number = CORE_BUDGET_BYTES, maxTools: number = CORE_MAX_TOOLS): string[] {
  const chosen: string[] = [];
  let used = 0;
  for (const name of ranking) {
    const size = sizes.get(name);
    if (size === undefined || used + size > budgetBytes) continue;
    chosen.push(name);
    used += size;
    if (chosen.length === maxTools) break;
  }
  return chosen;
}
