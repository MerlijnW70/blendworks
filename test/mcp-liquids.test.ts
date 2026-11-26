import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadIntents } from "../bench/tool-selection/intents.js";
import { buildInstructions } from "../src/mcp/instructions.js";
import { FAMILY_LINES } from "../src/mcp/routing/families.js";
import { WORKFLOWS } from "../src/mcp/routing/workflows.js";

const PATH_200 = `/${"w".repeat(199)}`;
const TOOLS = ["blender_liquid_body", "blender_liquid_fill", "blender_material_liquid"];

function presetNames(): string[] {
  const source = readFileSync("bridge/blendworks_bridge/liquid_presets.py", "utf8");
  const start = source.indexOf("PRESETS = {");
  const body = source.slice(start, source.indexOf("\n}\n", start));
  return [...body.matchAll(/^ {4}"([a-z_]+)": \{/gm)].map((match) => match[1]!);
}

describe("liquids in the MCP server and the docs", () => {
  it("sends the liquids family line, naming all three tools, with no other line dropped", () => {
    const line = FAMILY_LINES.find((entry) => entry.family === "liquids");
    for (const tool of TOOLS) expect(line?.text).toContain(tool);
    const plan = buildInstructions(PATH_200);
    expect(plan.included).toContain("liquids");
    expect(plan.dropped).toEqual([]);
    expect(plan.text).toContain(line!.text);
  });

  it("serves a liquids workflow naming every preset, and benchmark intents for every liquid tool", () => {
    const workflow = WORKFLOWS.find((entry) => entry.id === "liquids");
    expect(workflow?.steps).toEqual(expect.arrayContaining([...TOOLS, "blender_weather", "blender_render_final"]));
    const presets = presetNames();
    expect(presets.length).toBeGreaterThanOrEqual(15);
    for (const name of presets) expect(workflow!.note, name).toContain(name);
    const expected = new Set(loadIntents().flatMap((intent) => intent.expect));
    for (const tool of TOOLS) expect(expected.has(tool), tool).toBe(true);
  });

  it("documents every command, preset and the examples, with a source for every preset", () => {
    const design = readFileSync("docs/DESIGN.md", "utf8");
    const section = design.slice(design.indexOf("### Liquids"), design.indexOf("## 2. The MCP server"));
    for (const tool of TOOLS) expect(section, tool).toContain(`\`${tool.replace("blender_", "")}\``);
    for (const name of presetNames()) expect(section, name).toContain(`\`${name}\``);
    for (const word of ["**Materials.**", "**Bodies.**", "**Containers.**", "**With the rest of the scene.**", "**Measured.**"]) expect(section, word).toContain(word);
    expect(design).toContain("| Liquids | `material_liquid`");
    const research = readFileSync("docs/research/liquids.md", "utf8");
    const keys = [...readFileSync("bridge/blendworks_bridge/liquid_presets.py", "utf8").matchAll(/"sources": \[([^\]]*)\]/g)].flatMap((match) => [...match[1]!.matchAll(/"([a-z0-9_]+)"/g)].map((key) => key[1]!));
    expect(keys.length).toBeGreaterThan(30);
    for (const key of keys) expect(research, key).toContain(`\`${key}\``);
    const examples = readFileSync("docs/examples/README.md", "utf8");
    for (const file of ["liquid_lake.py", "liquid_still_life.py"]) expect(examples, file).toContain(file);
  });
});
