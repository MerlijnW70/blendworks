import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { repoRoot } from "../../scripts/lib/paths.js";
import { NATURAL_CLASSES } from "../../src/judge/natural-spec.js";
import { naturalRules } from "../../src/judge/natural.js";
import { parseSpec } from "../../src/judge/spec.js";

const RUBRIC = ["no-primitive", "multi-scale", "no-repetition", "weathering", "material-variation"];

describe("the natural spec templates", () => {
  for (const kind of NATURAL_CLASSES) {
    const path = join(repoRoot, "docs", "templates", `natural-${kind}.spec.json`);

    it(`natural-${kind} is a valid spec with the ${kind} rules and the five natural rubric criteria`, () => {
      const spec = parseSpec(JSON.parse(readFileSync(path, "utf8")));
      expect(spec.natural?.class).toBe(kind);
      expect(spec.visual?.rubric.map((criterion) => criterion.id)).toEqual(RUBRIC);
      expect(spec.visual?.required ?? false).toBe(false);
      expect(naturalRules(spec.natural, undefined).length).toBeGreaterThan(0);
    });

    it(`natural-${kind} is documented in DESIGN.md`, () => {
      const design = readFileSync(join(repoRoot, "docs", "DESIGN.md"), "utf8");
      expect(design).toContain(`natural-${kind}.spec.json`);
      for (const criterion of RUBRIC) expect(design).toContain(`| \`${criterion}\` |`);
    });
  }
});
