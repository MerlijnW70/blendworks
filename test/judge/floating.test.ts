import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeTextureFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(withWorkBudget(180_000, () => {
  assets = makeTextureFixtures("floating");
  specs = freshDir("floating", "specs");
}));

async function judged(asset: string, parts: Record<string, unknown>, label: string): Promise<Report> {
  const name = `${asset.replace(/\W+/g, "-")}-${label}`;
  const spec = join(specs, `${name}.spec.json`);
  writeFileSync(spec, JSON.stringify({ name: "body and lamp", format: "glb", parts, views: ["front"] }));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("floating", "reports", name), preview: true });
}

describe("floating parts", workBudget(120_000), () => {
  it("fails maxFloating 0 for the stray block and the lamp hanging 0.5 m above the body", async () => {
    const report = await judged("floating.glb", { maxFloating: 0 }, "zero");
    expect(report.measurements?.floating).toEqual({
      tolerance: 0.001,
      parts: 4,
      count: 2,
      items: [
        { object: "Body", index: 2, bounds: { min: [1, -0.1, 0], max: [1.2, 0.1, 0.2] } },
        { object: "Lamp", index: 0, bounds: { min: [-0.1, -0.1, 1.3], max: [0.1, 0.1, 1.5] } },
      ],
    });
    expect(report.rules.find((rule) => rule.rule === "parts.maxFloating")).toEqual({
      rule: "parts.maxFloating",
      measured: { floating: 2, parts: ["Body part 2", "Lamp part 0"], tolerance: 0.001 },
      limit: 0,
      pass: false,
    });
    expect(report.passed).toBe(false);
    expect(report.summary).toContain("FAIL  parts.maxFloating  measured floating 2, parts [Body part 2, Lamp part 0], tolerance 0.001; required at most 0");
    expect((await judged("floating.glb", { maxFloating: 2 }, "two")).passed).toBe(true);
  });

  it("passes when the same parts touch: the block against the base, the lamp on the top", async () => {
    const report = await judged("touching.glb", { maxFloating: 0 }, "zero");
    expect(report.measurements?.floating).toEqual({ tolerance: 0.001, parts: 4, count: 0, items: [] });
    expect(report.passed).toBe(true);
    expect(report.measurements?.manifold.looseParts).toBe(4);
  });

  it("measures the 0.5 mm gap under the lamp with the stated tolerance", async () => {
    expect((await judged("near.glb", { maxFloating: 0 }, "default")).measurements?.floating?.count).toBe(0);
    expect((await judged("near.glb", { maxFloating: 0, tolerance: 0.0006 }, "wide")).measurements?.floating?.count).toBe(0);
    const tight = await judged("near.glb", { maxFloating: 0, tolerance: 0.0004 }, "tight");
    expect(tight.measurements?.floating).toEqual({
      tolerance: 0.0004,
      parts: 4,
      count: 1,
      items: [{ object: "Lamp", index: 0, bounds: { min: [-0.1, -0.1, 0.8005], max: [0.1, 0.1, 1.0005] } }],
    });
    expect(tight.passed).toBe(false);
  });

  it("does not count a single-part asset as floating", async () => {
    const report = await judged("plain.glb", { maxFloating: 0 }, "single");
    expect(report.measurements?.floating).toEqual({ tolerance: 0.001, parts: 1, count: 0, items: [] });
    expect(report.passed).toBe(true);
  });
});
