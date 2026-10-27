import { existsSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge, type JudgeOptions } from "../../src/judge/run.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtures("verdict"));
  specs = freshDir("verdict", "specs");
}));

function judged(name: string, asset: string, options: Partial<JudgeOptions> = {}, overrides: Record<string, unknown> = {}): Promise<Report> {
  const spec = writeSpec(specs, name, { views: ["front", "three-quarter"], ...overrides });
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("verdict", "reports", name), device: "cpu", ...options });
}

function verdict(report: Report) {
  return { passed: report.passed, failure: report.failure, rules: report.rules.map((rule) => [rule.rule, rule.pass, rule.measured]) };
}

describe("the verdict depends on the measurements only", workBudget(180_000), () => {
  it("gives the same verdict on a machine too slow to render: a 1 ms render timeout is reported, and the rules stand", async () => {
    for (const asset of ["crate.glb", "wrong-size.glb"]) {
      const fast = await judged(`fast-${asset}`, asset);
      const slow = await judged(`slow-${asset}`, asset, { renderTimeoutMs: 1 });
      expect(fast.renders).toMatchObject({ status: "rendered", failure: null });
      expect(fast.renders?.views).toHaveLength(2);
      expect(slow.renders).toMatchObject({ status: "failed", views: [], failure: { stage: "render", code: "timeout" } });
      expect(verdict(slow)).toEqual(verdict(fast));
      expect(slow.passed).toBe(asset === "crate.glb");
      expect(slow.summary).toContain("views: not rendered (render failed: Blender took longer than 0.001 s and was stopped); the rules alone decide pass or fail");
      expect(existsSync(slow.renders!.contactSheet!)).toBe(true);
    }
  });

  it("fails renders.required when the render times out, and passes it when the views render", async () => {
    const slow = await judged("required-slow", "crate.glb", { renderTimeoutMs: 1 }, { renders: { required: true } });
    expect(slow.passed).toBe(false);
    expect(slow.failure).toBeNull();
    expect(slow.rules.filter((rule) => !rule.pass)).toEqual([
      { rule: "renders.required", measured: "failed: Blender took longer than 0.001 s and was stopped", limit: "rendered", pass: false },
    ]);
    const rendered = await judged("required-fast", "crate.glb", {}, { renders: { required: true }, views: ["front"] });
    expect(rendered.passed).toBe(true);
    expect(rendered.rules.find((rule) => rule.rule === "renders.required")).toEqual({ rule: "renders.required", measured: "rendered", limit: "rendered", pass: true });
    expect(rendered.renders?.views[0]?.sha256).toMatch(/^[0-9a-f]{64}$/);
  });

  it("skips views over the render triangle budget without touching the verdict, and renders.required fails then", async () => {
    const skipped = await judged("budget", "crate.glb", { renderMaxTriangles: 11 });
    expect(skipped.passed).toBe(true);
    expect(skipped.renders).toMatchObject({
      status: "skipped",
      reason: "over the render budget: 12 triangles, at most 11",
      views: [],
      budget: { triangles: 12, samplePixels: 2 * 512 * 512 * 24, maxTriangles: 11 },
    });
    const required = await judged("budget-required", "crate.glb", { renderMaxTriangles: 11 }, { renders: { required: true } });
    expect(required.rules.filter((rule) => !rule.pass).map((rule) => rule.rule)).toEqual(["renders.required"]);
  });

  it("gives the same verdict in preview mode, which renders nothing", async () => {
    const full = await judged("full", "wrong-size.glb", {}, { views: ["front"] });
    const preview = await judged("preview", "wrong-size.glb", { preview: true }, { views: ["front"] });
    expect(verdict(preview)).toEqual(verdict(full));
    expect(preview.renders?.status).toBe("preview");
  });
});
