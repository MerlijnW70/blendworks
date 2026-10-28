import { FAMILY_LINES, type FamilyLine } from "./routing/families.js";
import { CALL_TOOL, PYTHON_TOOL, SEARCH_TOOL } from "./routing/names.js";
import { GOAL_LIST, headlineGoals, WORKFLOWS } from "./routing/workflows.js";

export const UPFRONT_TEXT_LIMIT = 4096;
export const DEFERRED_TEXT_LIMIT = 16_384;
export const WORKSPACE_RESERVE = 200;
export const TIER0_LIMIT = 1500;

export interface InstructionPlan {
  text: string;
  tier0: number;
  included: string[];
  dropped: string[];
}

export function tier0Head(workspace: string): string[] {
  return [
    "Build 3D assets in Blender with the blender_ tools.",
    `- Every file path is inside the workspace ${workspace}; give paths relative to it.`,
    "- Work in metres; angles are in degrees.",
    `- Many clients list only the core tools. Find others with ${SEARCH_TOOL}: a query ("round the edges") returns the best tools with schemas and an example call; a goal returns a workflow's steps and notes. Call a found tool by name, or via ${CALL_TOOL} with tool and arguments; both check them against its schema.`,
    `- Goals include ${headlineGoals().join(", ")}; goal "${GOAL_LIST}" names all ${WORKFLOWS.length}.`,
    "- Check with blender_render_preview often (focus for close-ups, shading clay or wireframe), and counts and sizes with blender_scene_info.",
    "- Texture in order: model, UV, materials, bake, then blender_export to asset.glb.",
    `- Build parts with the shape tools, not by hand; use ${PYTHON_TOOL} only when no other tool can.`,
    "- Save a blender_checkpoint before risky steps. The headless session autosaves; after a crash, timeout or cancel it restarts and names the restored state. Every tool takes timeout_seconds.",
  ];
}

export const TIER0_TAIL = `- For anything else, ask ${SEARCH_TOOL}: it knows every tool, with its parameters, and every workflow.`;

function bullet(line: FamilyLine): string {
  return `- ${line.text}`;
}

export function byPriority(lines: FamilyLine[]): FamilyLine[] {
  return [...lines].sort((left, right) => left.priority - right.priority || left.family.localeCompare(right.family));
}

export function buildInstructions(workspace: string, budget: number = UPFRONT_TEXT_LIMIT, lines: FamilyLine[] = FAMILY_LINES): InstructionPlan {
  const head = tier0Head(workspace);
  const reserve = Math.max(0, WORKSPACE_RESERVE - workspace.length);
  const tier0 = [...head, TIER0_TAIL].join("\n").length;
  let used = tier0 + reserve;
  const included: FamilyLine[] = [];
  const dropped: string[] = [];
  for (const line of byPriority(lines)) {
    const cost = bullet(line).length + 1;
    if (used + cost <= budget) {
      included.push(line);
      used += cost;
    } else dropped.push(line.family);
  }
  return {
    text: [...head, ...included.map(bullet), TIER0_TAIL].join("\n"),
    tier0,
    included: included.map((line) => line.family),
    dropped,
  };
}

export function serverInstructions(workspace: string): string {
  return buildInstructions(workspace).text;
}
