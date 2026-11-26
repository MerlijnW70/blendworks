import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { loadIntents } from "../bench/tool-selection/intents.js";
import { buildInstructions } from "../src/mcp/instructions.js";
import { FAMILY_LINES } from "../src/mcp/routing/families.js";
import { WORKFLOWS } from "../src/mcp/routing/workflows.js";

const PATH_200 = `/${"w".repeat(199)}`;
const TOOLS = ["blender_weather", "blender_sky", "blender_clouds"];

function namesIn(path: string, table: string): string[] {
  const source = readFileSync(path, "utf8");
  const start = source.indexOf(`${table} = {`);
  const body = source.slice(start, source.indexOf("\n}\n", start));
  return [...body.matchAll(/^ {4}"([a-z_]+)": \{/gm)].map((match) => match[1]!);
}

describe("sky and weather in the MCP server and the docs", () => {
  it("sends the weather family line, naming all three tools, in the instructions", () => {
    const line = FAMILY_LINES.find((entry) => entry.family === "weather");
    for (const tool of TOOLS) expect(line?.text).toContain(tool);
    const plan = buildInstructions(PATH_200);
    expect(plan.included).toContain("weather");
    expect(plan.dropped).toEqual([]);
    expect(plan.text).toContain(line!.text);
  });

  it("serves a weather workflow and benchmark intents for every weather tool", () => {
    const workflow = WORKFLOWS.find((entry) => entry.id === "sky-weather");
    expect(workflow?.steps).toEqual(expect.arrayContaining([...TOOLS, "blender_render_final"]));
    for (const word of ["fair_cumulus", "thunderstorm", "storm 0-1", "time_of_day", "form auto"]) expect(workflow!.note).toContain(word);
    const expected = new Set(loadIntents().flatMap((intent) => intent.expect));
    for (const tool of TOOLS) expect(expected.has(tool), tool).toBe(true);
  });

  it("documents every command, preset, genus and time of day, and the example", () => {
    const design = readFileSync("docs/DESIGN.md", "utf8");
    const section = design.slice(design.indexOf("### Sky and weather"), design.indexOf("## 2. The MCP server"));
    const presets = namesIn("bridge/blendworks_bridge/weather_continuum.py", "PRESETS");
    const genera = namesIn("bridge/blendworks_bridge/cloud_genera.py", "GENERA");
    const times = namesIn("bridge/blendworks_bridge/weather_continuum.py", "TIMES");
    expect(presets.length).toBe(14);
    expect(genera.length).toBe(8);
    for (const name of [...presets, ...genera, ...times]) expect(section, name).toContain(`\`${name}\``);
    for (const tool of TOOLS) expect(section, tool).toContain(`\`${tool.replace("blender_", "")}\``);
    for (const word of ["**World fixes.**", "**Forms and cost.**", "**The continuum.**", "**Rain.**", "**Wet ground.**", "**Lightning.**"]) expect(section, word).toContain(word);
    expect(design).toContain("| Weather | `sky`");
    expect(readFileSync("docs/examples/README.md", "utf8")).toContain("weather_scene.py");
  });
});
