import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot } from "../../scripts/lib/paths.js";
import { naturalRules, RENDERED_RULES } from "../../src/judge/natural.js";
import { parseSpec } from "../../src/judge/spec.js";

function template(name: string) {
  return parseSpec(JSON.parse(readFileSync(join(repoRoot, "docs", "templates", `${name}.spec.json`), "utf8")));
}

function ruleNames(name: string): string[] {
  const spec = template(name);
  return [...naturalRules(spec.natural, undefined), ...naturalRules(spec.natural, undefined, RENDERED_RULES)].map((rule) => rule.rule);
}

describe("the natural templates with the rules of part two", () => {
  it("check repetition in every class template, and instances and sizes in the plant template", () => {
    for (const name of ["natural-rock", "natural-tree", "natural-plant"]) expect(ruleNames(name)).toContain("natural.repetition");
    expect(ruleNames("natural-plant")).toEqual(expect.arrayContaining(["natural.instanceRepetition", "natural.sizeDistribution"]));
  });

  it("give a grown tree Leonardo's rule and a forest the trunk-diameter law of Enquist and Niklas", () => {
    expect(ruleNames("natural-tree-skeleton")).toEqual(["natural.leonardo", "natural.repetition"]);
    const forest = template("natural-forest");
    expect(forest.natural?.sizeDistribution).toEqual({ min: -2.5, max: -1.5, by: "trunk" });
    expect(ruleNames("natural-forest")).toEqual(["natural.instanceRepetition", "natural.leonardo", "natural.sizeDistribution", "natural.repetition"]);
  });

  it("are documented in DESIGN.md", () => {
    const design = readFileSync(join(repoRoot, "docs", "DESIGN.md"), "utf8");
    for (const name of ["natural-tree-skeleton", "natural-forest"]) expect(design).toContain(`${name}.spec.json`);
  });
});
