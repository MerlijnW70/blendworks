import { describe, expect, it } from "vitest";
import { coreSources, derivedCoreScores } from "../bench/tool-selection/core-data.js";
import { docsFigures, grouped, NUMBERS_END, NUMBERS_START, quotedFigures, staleFigures, withFigures } from "../bench/tool-selection/docs-numbers.js";
import { loadIntents } from "../bench/tool-selection/intents.js";
import { buildInstructions, serverInstructions, TIER0_LIMIT, TIER0_TAIL, UPFRONT_TEXT_LIMIT, WORKSPACE_RESERVE } from "../src/mcp/instructions.js";
import { CORE_FILL } from "../src/mcp/routing/core.generated.js";
import { chooseCore, CORE_HYSTERESIS, CORE_LIMITS, CORE_PINNED, coreScores, type FillLimits, updateFill } from "../src/mcp/routing/core.js";
import { FAMILY_LINES, type FamilyLine, MAX_FAMILY_LINE } from "../src/mcp/routing/families.js";
import { find } from "../src/mcp/routing/router.js";
import { ToolSearch } from "../src/mcp/routing/search.js";
import { headlineGoals, WORKFLOWS, type Workflow } from "../src/mcp/routing/workflows.js";

const PATH_200 = `/${"w".repeat(WORKSPACE_RESERVE - 1)}`;
const MOVED_DETAIL = ["around_z", "vein_softness", "hard_cells", "atlas_sizes", "min_island_area", "with_masks", "uv_checker", "bottom_centre", "solver auto", "closed true"];

function filler(count: number, length = 150): FamilyLine[] {
  return Array.from({ length: count }, (_, index) => ({ family: `extra_${index}`, priority: 90 + index, text: `Extra ${index}: ${"x".repeat(length)}.` }));
}

describe("tiered server instructions", () => {
  it("always fit Tier 0 with a 200-character workspace path, whatever Tier 1 holds", () => {
    const bare = buildInstructions(PATH_200, UPFRONT_TEXT_LIMIT, []);
    expect(bare.tier0).toBeLessThanOrEqual(TIER0_LIMIT);
    expect(bare.text.length).toBe(bare.tier0);
    const lines = bare.text.split("\n");
    expect(lines[1]).toContain(PATH_200);
    expect(lines[2]).toContain("metres");
    expect(lines[3]).toContain("blender_find_tools");
    expect(lines[3]).toContain("blender_call");
    for (const word of ["blender_render_preview", "Texture in order: model, UV, materials, bake", "shape tools", "blender_run_python", "blender_checkpoint", "timeout_seconds"]) expect(bare.text).toContain(word);
    expect(lines.at(-1)).toBe(TIER0_TAIL);
    const crowded = buildInstructions(PATH_200, UPFRONT_TEXT_LIMIT, [...FAMILY_LINES, ...filler(40)]);
    expect(crowded.text.startsWith(bare.text.slice(0, -TIER0_TAIL.length))).toBe(true);
    expect(crowded.text.endsWith(`\n${TIER0_TAIL}`)).toBe(true);
  });

  it("never exceed the 4,096-character budget, for any path up to 200 characters and any number of lines", () => {
    for (const length of [1, 20, 80, 150, 199, 200]) {
      const workspace = `/${"p".repeat(length - 1)}`;
      for (const lines of [FAMILY_LINES, [...FAMILY_LINES, ...filler(5)], [...FAMILY_LINES, ...filler(60, 40)], filler(200, 10)]) {
        const plan = buildInstructions(workspace, UPFRONT_TEXT_LIMIT, lines);
        expect(plan.text.length + Math.max(0, WORKSPACE_RESERVE - workspace.length), `${length} characters, ${lines.length} lines`).toBeLessThanOrEqual(UPFRONT_TEXT_LIMIT);
        expect(plan.included.length + plan.dropped.length).toBe(lines.length);
      }
    }
    const longPath = `/${"q".repeat(399)}`;
    expect(buildInstructions(longPath, UPFRONT_TEXT_LIMIT, [...FAMILY_LINES, ...filler(30)]).text.length).toBeLessThanOrEqual(UPFRONT_TEXT_LIMIT);
  });

  it("send the same Tier 1 lines for every workspace path up to the 200 characters reserved for it", () => {
    const reference = buildInstructions(PATH_200).included;
    expect(buildInstructions("/w").included).toEqual(reference);
    expect(serverInstructions(PATH_200)).toBe(buildInstructions(PATH_200).text);
  });

  it("add Tier 1 lines by priority and report a dropped line by its family", () => {
    const lines: FamilyLine[] = [
      { family: "late", priority: 50, text: "Late: blender_late." },
      { family: "early", priority: 10, text: "Early: blender_early." },
      { family: "dummy", priority: 30, text: `Dummy: ${"d".repeat(200)}.` },
    ];
    const bare = buildInstructions(PATH_200, UPFRONT_TEXT_LIMIT, []).text.length;
    const plan = buildInstructions(PATH_200, bare + 50, lines);
    expect(plan.included).toEqual(["early", "late"]);
    expect(plan.dropped).toEqual(["dummy"]);
    expect(plan.text).not.toContain("Dummy:");
    expect(plan.text.indexOf("- Early:")).toBeLessThan(plan.text.indexOf("- Late:"));
    const roomy = buildInstructions(PATH_200, UPFRONT_TEXT_LIMIT, lines);
    expect(roomy.dropped).toEqual([]);
    expect(roomy.text.indexOf("- Dummy:")).toBeLessThan(roomy.text.indexOf("- Late:"));
  });

  it("take Tier 1 from one short line per family", () => {
    const families = FAMILY_LINES.map((line) => line.family);
    expect(new Set(families).size).toBe(families.length);
    for (const line of FAMILY_LINES) {
      expect(line.text, line.family).not.toContain("\n");
      expect(line.text.length, line.family).toBeLessThanOrEqual(MAX_FAMILY_LINE);
      expect(Number.isInteger(line.priority), line.family).toBe(true);
    }
    expect(buildInstructions(PATH_200).text.length).toBeLessThanOrEqual(UPFRONT_TEXT_LIMIT);
  });
});

describe("workflow goals through the router", () => {
  it("name only a few headline goals in the instructions, and serve every goal with goal list", () => {
    const instructions = serverInstructions(PATH_200);
    const headlines = headlineGoals();
    expect(headlines.length).toBeGreaterThanOrEqual(3);
    expect(headlines.length).toBeLessThanOrEqual(8);
    for (const goal of headlines) expect(instructions).toContain(goal);
    expect(instructions).toContain('goal "list"');
    const others = WORKFLOWS.filter((workflow) => workflow.headline !== true);
    expect(others.filter((workflow) => instructions.includes(workflow.goal.toLowerCase())).map((workflow) => workflow.id)).toEqual([]);
    const listed = find(new ToolSearch([]), { goal: " List ", limit: 5 });
    const text = listed.result.content.map((part) => (part.type === "text" ? part.text : "")).join("");
    for (const workflow of WORKFLOWS) expect(text, workflow.id).toContain(`- ${workflow.goal}: ${workflow.examples.join("; ")}.`);
    expect(text).not.toContain("No tool matches");
    expect(listed.names).toEqual([]);
  });

  it("keep parameter detail out of the instructions and in the workflow notes", () => {
    const instructions = serverInstructions(PATH_200);
    const notes = WORKFLOWS.map((workflow) => workflow.note).join("\n");
    for (const word of MOVED_DETAIL) {
      expect(instructions, word).not.toContain(word);
      expect(notes, word).toContain(word);
    }
  });
});

const ROOMY: FillLimits = { pinned: ["p1", "p2"], maxTools: 5, budgetBytes: 1000, hysteresis: 0.25 };

function sizesOf(names: string[], size = 10): Map<string, number> {
  return new Map(names.map((name) => [name, size]));
}

describe("the pinned core and its data fill", () => {
  it("always lists the pinned tools, even when they alone exceed the byte budget", () => {
    const sizes = new Map([["p1", 900], ["p2", 900], ["a", 10]]);
    expect(chooseCore(["p1", "p2"], ["a"], sizes, 1000, 5)).toEqual(["p1", "p2"]);
    expect(chooseCore(["p1", "missing", "p2"], ["a"], new Map([["p1", 10], ["p2", 10], ["a", 10]]), 1000, 5)).toEqual(["p1", "p2", "a"]);
    expect(CORE_PINNED).toContain("library_apply");
    expect(CORE_PINNED.length).toBeGreaterThanOrEqual(8);
    expect(CORE_PINNED.length).toBeLessThanOrEqual(10);
    expect(CORE_PINNED.length + CORE_FILL.length).toBeLessThanOrEqual(CORE_LIMITS.maxTools);
    expect(CORE_FILL.filter((name) => CORE_PINNED.includes(name))).toEqual([]);
  });

  it("swaps a fill member only when an outsider scores more than the hysteresis above it", () => {
    const names = ["p1", "p2", "a", "b", "c", "d"];
    const scores = new Map([["p1", 9], ["p2", 9], ["a", 4], ["b", 3], ["c", 2], ["d", 1.75]]);
    const fresh = updateFill([], scores, sizesOf(names), ROOMY);
    expect(fresh).toEqual(["a", "b", "c"]);
    scores.set("d", 2 + ROOMY.hysteresis);
    expect(updateFill(fresh, scores, sizesOf(names), ROOMY)).toEqual(fresh);
    scores.set("d", 2 + ROOMY.hysteresis + 0.125);
    expect(updateFill(fresh, scores, sizesOf(names), ROOMY)).toEqual(["a", "b", "d"]);
    expect(updateFill(["a", "b", "gone"], scores, sizesOf(names), ROOMY)).toEqual(["a", "b", "d"]);
  });

  it("fills only with tools that fit in the bytes the pinned tools leave", () => {
    const sizes = new Map([["p1", 300], ["p2", 300], ["big", 500], ["a", 100], ["b", 100], ["c", 100]]);
    const scores = new Map([["big", 0.9], ["a", 0.5], ["b", 0.4], ["c", 0.3]]);
    expect(updateFill([], scores, sizes, ROOMY)).toEqual(["a", "b", "c"]);
    expect(updateFill(["big"], scores, sizes, ROOMY)).toEqual(["a", "b", "c"]);
  });

  it("scores each source over a fixed denominator, so one more workflow step moves only its tool, by one step", () => {
    const before = derivedCoreScores();
    const step: Workflow = { id: "extra", goal: "Extra", examples: ["extra"], steps: ["blender_bevel"], note: "Extra." };
    const after = derivedCoreScores({ workflows: [...WORKFLOWS, step] });
    const perStep = 1 / coreSources().workflows.denominator;
    expect(perStep).toBeLessThan(CORE_HYSTERESIS);
    for (const [name, score] of before) {
      if (name === "blender_bevel") expect(after.get(name)! - score).toBeCloseTo(perStep, 12);
      else expect(after.get(name), name).toBe(score);
    }
    expect(coreScores([{ counts: { a: 1 }, denominator: 4 }, { counts: { a: 1, b: 2 }, denominator: 2 }])).toEqual(new Map([["a", 0.75], ["b", 1]]));
  });

  it("keeps the core when one workflow step is added to any tool, unless that lifts it past the hysteresis", () => {
    const scores = derivedCoreScores();
    const names = [...scores.keys()];
    const sizes = sizesOf(names);
    const fill = updateFill([], scores, sizes);
    const weakest = Math.min(...fill.map((name) => scores.get(name)!));
    for (const name of names.filter((entry) => !fill.includes(entry) && !CORE_PINNED.includes(entry))) {
      const workflows = [...WORKFLOWS, { id: "one", goal: "One", examples: ["one"], steps: [name], note: "One." }];
      const lifted = derivedCoreScores({ workflows });
      const changed = updateFill(fill, lifted, sizes);
      expect(changed.includes(name), name).toBe(lifted.get(name)! - weakest > CORE_HYSTERESIS);
    }
  });

  it("keeps the core when a dummy command gets two workflow steps", () => {
    const scores = derivedCoreScores();
    const sizes = sizesOf([...scores.keys(), "blender_dummy"]);
    const fill = updateFill([], scores, sizes);
    const dummy: Workflow = { id: "dummy", goal: "Dummy", examples: ["dummy"], steps: ["blender_dummy", "blender_dummy"], note: "Dummy." };
    expect(updateFill(fill, derivedCoreScores({ workflows: [...WORKFLOWS, dummy] }), sizes)).toEqual(fill);
    const intents = loadIntents();
    expect(updateFill(fill, derivedCoreScores({ intents, workflows: [...WORKFLOWS, { ...dummy, steps: ["blender_lathe", "blender_dummy"] }] }), sizes)).toEqual(fill);
  });
});

describe("the figures docs/DESIGN.md quotes", () => {
  const figures = [
    { label: "Tools (bridge commands and library tools)", value: "115" },
    { label: "Benchmark intents", value: "283" },
  ];

  it("name a stale, a missing and an unknown figure", () => {
    const current = withFigures(`intro\n${NUMBERS_START}\n${NUMBERS_END}\nrest`, figures);
    expect(current).toContain("| Benchmark intents | 283 |");
    expect(staleFigures(current, figures)).toEqual([]);
    const stale = current.replace("| 115 |", "| 114 |");
    expect(staleFigures(stale, figures)).toEqual(['docs/DESIGN.md says "Tools (bridge commands and library tools)" is 114, but npm run bench:tools prints 115']);
    expect(staleFigures(current, [...figures, { label: "Held-out intents", value: "113" }])).toEqual(['docs/DESIGN.md does not quote "Held-out intents" (113)']);
    expect(staleFigures(current, figures.slice(1))).toEqual(['docs/DESIGN.md quotes "Tools (bridge commands and library tools)", which npm run bench:tools no longer prints']);
    expect(quotedFigures("no table")).toEqual(new Map());
  });

  it("print the instruction figures from the same builder the server uses", () => {
    const printed = new Map(docsFigures({ all: [], core: [], intents: loadIntents() }).map((figure) => [figure.label, figure.value]));
    const plan = buildInstructions(PATH_200);
    expect(printed.get("Instructions with a 200-character workspace path, characters")).toBe(grouped(plan.text.length));
    expect(printed.get("Tier 0 of the instructions, characters")).toBe(grouped(plan.tier0));
    expect(printed.get("Held-out intents")).toBe("113");
    expect(grouped(76543)).toBe("76 543");
  });
});
