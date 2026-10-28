import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { buildInstructions, WORKSPACE_RESERVE } from "../src/mcp/instructions.js";
import { FAMILY_LINES } from "../src/mcp/routing/families.js";
import { WORKFLOWS } from "../src/mcp/routing/workflows.js";

const TOOLS = ["blender_camera_setup", "blender_atmosphere", "blender_render_final"];

describe("photography tools in the MCP server", () => {
  it("send the photography family line, naming all three tools, in the instructions", () => {
    const line = FAMILY_LINES.find((entry) => entry.family === "photography");
    expect(line).toBeDefined();
    for (const tool of TOOLS) expect(line!.text).toContain(tool);
    const plan = buildInstructions(`/${"w".repeat(WORKSPACE_RESERVE - 1)}`);
    expect(plan.text).toContain(line!.text);
  });

  it("serve a photographic look workflow that ends in a final render", () => {
    const workflow = WORKFLOWS.find((entry) => entry.id === "photographic-look");
    expect(workflow).toBeDefined();
    expect(workflow!.steps).toEqual(expect.arrayContaining(TOOLS));
    expect(workflow!.steps.at(-1)).toBe("blender_render_final");
    for (const word of ["fstop", "focus_object", "shutter", "visibility", "time_limit", "passes"]) expect(workflow!.note).toContain(word);
  });

  it("document every photography command and its numbers in the design", () => {
    const design = readFileSync("docs/DESIGN.md", "utf8");
    const section = design.slice(design.indexOf("### Final renders"), design.indexOf("## 2. The MCP server"));
    for (const word of ["`camera_setup`", "`atmosphere`", "`render_final`", "EV100 = log2(N^2 / t) - log2(ISO / 100)", "3.912 / visibility", "**Cost:**", "**Fallback:**", "**Determinism:**", "**Photographic look**"]) {
      expect(section, word).toContain(word);
    }
    expect(design).toContain("| Photography | `camera_setup`");
  });
});
