import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { main } from "../../src/judge/cli.js";
import { DEFAULTS, judge, type JudgeOptions } from "../../src/judge/run.js";
import { detectTools, planSandbox } from "../../src/judge/sandbox.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtures("preview"));
  specs = freshDir("preview", "specs");
}));

function judged(name: string, asset: string, options: Partial<JudgeOptions> = {}, overrides: Record<string, unknown> = {}) {
  const spec = writeSpec(specs, name, { views: ["front", "three-quarter"], ...overrides });
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("preview", "reports", name), ...options });
}

function isPng(path: string): boolean {
  return statSync(path).size > 1000 && readFileSync(path).subarray(1, 4).toString("latin1") === "PNG";
}

describe("preview mode", workBudget(120_000), () => {
  it("checks every rule and draws the UV layout, but renders no views", async () => {
    const report = await judged("crate", "crate.glb", { preview: true, device: "gpu", backends: [] });
    expect(report.passed).toBe(true);
    expect(report.rules.map((rule) => rule.rule)).toContain("uv.maxOverlap");
    expect(report.preview).toBe(true);
    expect(report.renders).toMatchObject({ viewsSkipped: true, views: [] });
    expect(report.device).toBeNull();
    expect(report.timings.render).toBeNull();
    expect(report.timings.measure).toBeGreaterThan(0);
    expect(report.timings.sheet).toBeGreaterThan(0);
    const outDir = join(report.renders!.contactSheet!, "..");
    expect(existsSync(join(outDir, "views"))).toBe(false);
    expect(isPng(report.renders!.contactSheet!)).toBe(true);
    expect(report.summary).toContain("views: skipped (preview); the rules alone decide pass or fail");
    expect(JSON.parse(readFileSync(join(outDir, "report.json"), "utf8")).renders.viewsSkipped).toBe(true);
  });

  it("fails on the rules alone", async () => {
    const report = await judged("wrong-size", "wrong-size.glb", { preview: true });
    expect(report.passed).toBe(false);
    expect(report.failure).toBeNull();
    expect(report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule)).toEqual(["size.x"]);
    expect(report.renders?.views).toEqual([]);
  });

  it("sets the exit code from the rules on the command line", async () => {
    const spec = writeSpec(specs, "command");
    const passOut = freshDir("preview", "command-pass");
    expect(await main(["judge", spec, join(assets, "crate.glb"), "--preview", "--no-require-isolation", "--out", passOut])).toBe(0);
    expect(await main(["judge", spec, join(assets, "wrong-size.glb"), "--preview", "--no-require-isolation", "--out", freshDir("preview", "command-fail")])).toBe(1);
    expect(existsSync(join(passOut, "contact-sheet.png"))).toBe(true);
    expect(existsSync(join(passOut, "views"))).toBe(false);
  });
});

describe("the render device on this machine", workBudget(120_000), () => {
  it("falls back to the CPU with the original limits when no GPU backend works", async () => {
    const report = await judged("no-gpu", "crate.glb", { device: "auto", backends: [] }, { views: ["front"] });
    expect(report.passed).toBe(true);
    expect(report.device).toMatchObject({ requested: "auto", kind: "cpu", fallback: "no usable GPU (no backend was probed)" });
    const view = { workDir: specs, writable: [specs], readOnly: [] };
    const original = planSandbox(blenderPath(), "judge.py", [], { timeoutMs: DEFAULTS.timeoutMs, memoryBytes: DEFAULTS.memoryBytes }, detectTools(blenderPath()), "cpu", view).isolation;
    expect(report.renderSandbox).toEqual(original);
    expect(report.renders?.views).toHaveLength(1);
    expect(isPng(report.renders!.views[0]!.path)).toBe(true);
    expect(report.summary).toContain("render: cpu (auto fell back to the CPU with the original limits: no usable GPU");
    expect(report.timings.device).toBeGreaterThanOrEqual(0);
  });

  it("reports cleanly under gpu when no GPU backend works, and the verdict stands on the measurements", async () => {
    const report = await judged("gpu-only", "crate.glb", { device: "gpu", backends: [] }, { views: ["front"] });
    expect(report.passed).toBe(true);
    expect(report.failure).toBeNull();
    expect(report.renders).toMatchObject({ status: "failed", views: [], failure: { stage: "device", code: "no_gpu" } });
    expect(report.renders?.failure?.message).toBe("BLENDWORKS_DEVICE=gpu, but no usable GPU (no backend was probed)");
    expect(isPng(report.renders!.contactSheet!)).toBe(true);
    expect(report.summary).toContain("views: not rendered (device failed: BLENDWORKS_DEVICE=gpu, but no usable GPU (no backend was probed)); the rules alone decide pass or fail");
  });

  it("gives the same image when re-run on the CPU", async () => {
    const first = await judged("again-1", "crate.glb", { device: "cpu" }, { views: ["three-quarter"] });
    const second = await judged("again-2", "crate.glb", { device: "cpu" }, { views: ["three-quarter"] });
    expect(first.device).toMatchObject({ kind: "cpu", fallback: null });
    expect(first.timings.device).toBeNull();
    expect(readFileSync(first.renders!.views[0]!.path).equals(readFileSync(second.renders!.views[0]!.path))).toBe(true);
  });

  it("names the device it rendered on", async () => {
    const report = await judged("auto", "crate.glb", { device: "auto" }, { views: ["front"] });
    expect(report.passed).toBe(true);
    expect(report.summary).toMatch(/\n {2}render: (gpu (OPTIX|CUDA|HIP|METAL|ONEAPI) \(.+\)|cpu \(auto fell back .+\))\n/);
    expect(report.timings.render).toBeGreaterThan(0);
  });
});
