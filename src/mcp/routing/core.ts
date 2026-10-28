export const CORE_PINNED: string[] = [
  "blender_new_scene",
  "blender_add_primitive",
  "blender_assign_material",
  "blender_uv_smart_project",
  "blender_bake",
  "blender_render_preview",
  "blender_scene_info",
  "blender_export",
  "library_apply",
];

export const CORE_MAX_TOOLS = 12;
export const CORE_BUDGET_BYTES = 40_000;
export const CORE_HYSTERESIS = 0.02;
export const CORE_WRITE_COMMAND = "npm run bench:core -- --write";

export interface RankingSource {
  counts: Record<string, number>;
  denominator: number;
}

export interface FillLimits {
  pinned: string[];
  maxTools: number;
  budgetBytes: number;
  hysteresis: number;
}

export const CORE_LIMITS: FillLimits = { pinned: CORE_PINNED, maxTools: CORE_MAX_TOOLS, budgetBytes: CORE_BUDGET_BYTES, hysteresis: CORE_HYSTERESIS };

export function coreScores(sources: RankingSource[]): Map<string, number> {
  const scores = new Map<string, number>();
  for (const source of sources) {
    if (!(source.denominator > 0)) throw new Error("a core ranking source needs a positive denominator");
    for (const [name, count] of Object.entries(source.counts)) scores.set(name, (scores.get(name) ?? 0) + count / source.denominator);
  }
  return scores;
}

export function rankCore(scores: Map<string, number>): string[] {
  return [...scores].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0])).map(([name]) => name);
}

export function chooseCore(pinned: string[], fill: string[], sizes: Map<string, number>, budgetBytes: number = CORE_BUDGET_BYTES, maxTools: number = CORE_MAX_TOOLS): string[] {
  const chosen = [...new Set(pinned)].filter((name) => sizes.has(name));
  let used = chosen.reduce((sum, name) => sum + sizes.get(name)!, 0);
  for (const name of fill) {
    const size = sizes.get(name);
    if (chosen.length >= maxTools) break;
    if (size === undefined || chosen.includes(name) || used + size > budgetBytes) continue;
    chosen.push(name);
    used += size;
  }
  return chosen;
}

export function updateFill(current: string[], scores: Map<string, number>, sizes: Map<string, number>, limits: FillLimits = CORE_LIMITS): string[] {
  const pinned = new Set(limits.pinned.filter((name) => sizes.has(name)));
  const score = (name: string) => scores.get(name) ?? 0;
  const size = (name: string) => sizes.get(name)!;
  const room = limits.budgetBytes - [...pinned].reduce((sum, name) => sum + size(name), 0);
  const slots = Math.max(0, limits.maxTools - pinned.size);
  const eligible = (name: string) => sizes.has(name) && !pinned.has(name) && score(name) > 0;
  const best = (left: string, right: string) => score(right) - score(left) || left.localeCompare(right);
  const fill = [...new Set(current)].filter(eligible).sort(best);
  const bytes = () => fill.reduce((sum, name) => sum + size(name), 0);
  while (fill.length > 0 && (fill.length > slots || bytes() > room)) fill.pop();
  const outsiders = () => [...scores.keys()].filter((name) => eligible(name) && !fill.includes(name)).sort(best);
  const fillUp = () => {
    for (const name of outsiders()) if (fill.length < slots && bytes() + size(name) <= room) fill.push(name);
  };
  const swapOnce = (): boolean => {
    const ascending = [...fill].reverse();
    for (const candidate of outsiders()) {
      const leaving = ascending.find((member) => score(candidate) - score(member) > limits.hysteresis && bytes() - size(member) + size(candidate) <= room);
      if (leaving !== undefined) {
        fill.splice(fill.indexOf(leaving), 1, candidate);
        fill.sort(best);
        return true;
      }
    }
    return false;
  };
  fillUp();
  while (swapOnce()) fillUp();
  return fill.sort(best);
}
