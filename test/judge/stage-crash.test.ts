import { mkdirSync, readFileSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { copyDelivery } from "../../src/judge/delivery.js";
import { runPass, type PassStage, type StageGroup } from "../../src/judge/onepass.js";
import { detectTools } from "../../src/judge/sandbox.js";
import { workOut, type Sandbox } from "../../src/judge/stages.js";
import { freshDir, makeFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const PROBE = fileURLToPath(new URL("./stage_crash_probe.py", import.meta.url));
const LIMITS_PROBE = fileURLToPath(new URL("./stage_limits_probe.py", import.meta.url));
const MEMORY = 4096 * 1024 * 1024;
const STAGES: PassStage[] = ["measure", "reference", "views", "sheet", "closeups"];
const ARGS = ["--reference-views", "front:32", "--reference-frame", "measured", "--views", "front", "--res", "32", "--samples", "1", "--closeup-res", "32", "--closeup-samples", "1"];
const BUDGETS: Record<StageGroup, number> = { measure: 120_000, reference: 120_000, render: 120_000, closeups: 120_000 };

let asset = "";

beforeAll(withWorkBudget(60_000, () => {
  asset = join(makeFixtures("stage-crash").assets, "crate.glb");
}));

function prepared(name: string): { sandbox: Sandbox; main: string } {
  const workDir = freshDir("stage-crash", name);
  const delivery = copyDelivery(asset, extname(asset).slice(1), workDir, 64 * 1024 * 1024);
  const sandbox: Sandbox = { blender: blenderPath(), limits: { timeoutMs: 120_000, memoryBytes: MEMORY }, tools: detectTools(blenderPath()), workDir, delivery: delivery.folder };
  mkdirSync(workOut(sandbox), { recursive: true });
  return { sandbox, main: delivery.main };
}

async function failIn(stage: PassStage, kind: "exit" | "hang", budgets: Record<StageGroup, number> = BUDGETS) {
  const { sandbox, main } = prepared(`${stage}-${kind}`);
  const args = [...ARGS, "--crash-stage", stage, "--crash-kind", kind];
  return runPass({ asset: main, stages: STAGES, args, device: "cpu", sandbox, budgets, script: PROBE });
}

describe("a stage that crashes or hangs in the one judge process", workBudget(240_000), () => {
  it.each([
    ["measure", "measure", []],
    ["reference", "reference", ["measure"]],
    ["views", "render", ["measure", "reference"]],
    ["closeups", "closeups", ["measure", "reference", "views", "sheet"]],
  ] as const)("is reported for the %s stage, with the timings of the stages before it", async (stage, group, before) => {
    const result = await failIn(stage, "exit");
    expect(result.interrupted).toMatchObject({ stage, failure: { stage: group, code: "crashed" } });
    expect(result.interrupted!.failure.message).toContain("exited with code 3");
    expect(result.records.map((record) => record.stage)).toEqual(before);
    for (const record of result.records) expect(record.ok && record.seconds >= 0 && record.endedAt >= result.spawnedAt).toBe(true);
  });

  it("times its stages on the judge's own monotonic clock, so a wall clock that jumps never makes a stage end before Blender started", async () => {
    const real = Date.now.bind(Date);
    const jumped = vi.spyOn(Date, "now").mockImplementation(() => real() + 60_000);
    try {
      const result = await failIn("closeups", "exit");
      expect(result.records.map((record) => record.stage)).toEqual(["measure", "reference", "views", "sheet"]);
      for (const record of result.records) expect(record.endedAt - result.spawnedAt, record.stage).toBeGreaterThanOrEqual(0);
      const ends = result.records.map((record) => record.endedAt);
      expect([...ends].sort((first, second) => first - second)).toEqual(ends);
    } finally {
      jumped.mockRestore();
    }
  });

  it("stops a stage that runs over its own budget and names that stage", async () => {
    const result = await failIn("sheet", "hang", { ...BUDGETS, render: 6_000 });
    expect(result.interrupted).toMatchObject({ stage: "sheet", failure: { stage: "render", code: "timeout", message: "Blender took longer than 6 s and was stopped" } });
    expect(result.records.map((record) => record.stage)).toEqual(["measure", "reference", "views"]);
  });
});

describe("the GPU sandbox of the one judge process", workBudget(120_000), () => {
  it.runIf(process.platform === "linux")("holds the address space to the memory cap while measuring, and lifts it only for the GPU probe", async () => {
    const { sandbox, main } = prepared("limits");
    const args = ["--views", "front", "--res", "32", "--samples", "1", "--device", "AUTO", "--backends", "OPTIX,CUDA", "--gpu-fallback", "yes"];
    const result = await runPass({ asset: main, stages: ["measure", "views", "sheet"], args, device: "gpu", sandbox, budgets: BUDGETS, addressSpaceUntilGpu: true, script: LIMITS_PROBE });
    expect(result.isolation.memory).toContain("address space 4096 MB until the GPU starts");
    const seen = JSON.parse(readFileSync(join(workOut(sandbox), "limits.json"), "utf8")) as Record<string, { addressSpace: number[]; data: number[]; unlimited: number }>;
    expect(seen.measure!.addressSpace).toEqual([MEMORY, seen.measure!.unlimited]);
    expect(seen.measure!.data).toEqual([MEMORY, MEMORY]);
    expect(seen.probe!.addressSpace).toEqual([seen.probe!.unlimited, seen.probe!.unlimited]);
    expect(seen.probe!.data).toEqual([MEMORY, MEMORY]);
  });
});
