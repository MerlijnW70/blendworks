import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadIntents } from "../bench/tool-selection/intents.js";
import { buildInstructions } from "../src/mcp/instructions.js";
import { FAMILY_LINES } from "../src/mcp/routing/families.js";
import { WORKFLOWS } from "../src/mcp/routing/workflows.js";

const PATH_200 = `/${"w".repeat(199)}`;
const TOOLS = ["blender_ground_element", "blender_ground_cover", "blender_ground_cover_export"];

function presetNames(): string[] {
  const source = readFileSync("bridge/blendworks_bridge/cover_presets.py", "utf8");
  const table = /PRESET_POPULATIONS = \{([^}]*)\}/.exec(source)?.[1] ?? "";
  return [...table.matchAll(/"([a-z_]+)":/g)].map((match) => match[1]!);
}

describe("ground cover in the MCP server and the docs", () => {
  it("names the ground cover tools in a family line that the instructions keep", () => {
    const line = FAMILY_LINES.find((entry) => entry.family === "ground_cover");
    expect(line?.text).toContain("blender_ground_cover");
    expect(line!.text.length).toBeLessThanOrEqual(80);
    const plan = buildInstructions(PATH_200);
    expect(plan.included).toContain("ground_cover");
    expect(plan.text).toContain(line!.text);
  });

  it("offers a ground cover workflow and benchmark intents for every ground cover tool", () => {
    const workflow = WORKFLOWS.find((entry) => entry.id === "ground-cover");
    expect(workflow?.steps).toEqual(expect.arrayContaining(["blender_ground_cover", "blender_ground_cover_export"]));
    expect(workflow?.examples).toEqual(expect.arrayContaining(["meadow", "lawn", "forest floor", "dry steppe"]));
    const expected = new Set(loadIntents().flatMap((intent) => intent.expect));
    for (const tool of TOOLS) expect(expected.has(tool), tool).toBe(true);
  });

  it("documents the commands, every preset, the wind colours and the example", () => {
    const design = readFileSync("docs/DESIGN.md", "utf8");
    const examples = readFileSync("docs/examples/README.md", "utf8");
    const presets = presetNames();
    expect(presets).toEqual(["meadow", "forest_floor", "dry_steppe", "lawn"]);
    for (const preset of presets) expect(design, preset).toContain(`\`${preset}\``);
    for (const tool of TOOLS) expect(design, tool).toContain(`\`${tool.replace("blender_", "")}\``);
    expect(design).toContain("R is the flutter weight");
    expect(design).toContain("EXT_mesh_gpu_instancing");
    expect(examples).toContain("meadow_cover.py");
  });
});
