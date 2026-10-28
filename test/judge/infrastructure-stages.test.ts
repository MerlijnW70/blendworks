import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { judgeAsset } from "../../src/judge/container/asset.js";
import { layoutFrom } from "../../src/judge/container/inputs.js";
import { copyDelivery } from "../../src/judge/delivery.js";
import { measuredFrom } from "../../src/judge/judge-pass.js";
import { runPass, type StageGroup } from "../../src/judge/onepass.js";
import { INFRASTRUCTURE_FILE, judge } from "../../src/judge/run.js";
import { detectTools } from "../../src/judge/sandbox.js";
import { StageFailure, workOut, type Sandbox } from "../../src/judge/stages.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const PROBE = fileURLToPath(new URL("./infrastructure_probe.py", import.meta.url));
const BUDGETS: Record<StageGroup, number> = { measure: 120_000, reference: 120_000, render: 120_000, closeups: 120_000 };

let asset = "";
let specs = "";

beforeAll(withWorkBudget(60_000, () => {
  asset = join(makeFixtures("infrastructure").assets, "crate.glb");
  specs = freshDir("infrastructure", "specs");
}));

function prepared(name: string): { sandbox: Sandbox; main: string; delivery: ReturnType<typeof copyDelivery> } {
  const workDir = freshDir("infrastructure", name);
  const delivery = copyDelivery(asset, extname(asset).slice(1), workDir, 64 * 1024 * 1024);
  const sandbox: Sandbox = { blender: blenderPath(), limits: { timeoutMs: 120_000, memoryBytes: 4096 * 1024 * 1024 }, tools: detectTools(blenderPath()), workDir, delivery: delivery.folder };
  mkdirSync(workOut(sandbox), { recursive: true });
  return { sandbox, main: delivery.main, delivery };
}

async function outcome(kind: string) {
  const { sandbox, main, delivery } = prepared(kind);
  const result = await runPass({ asset: main, stages: ["measure"], args: ["--outcome", kind], device: "cpu", sandbox, budgets: BUDGETS, script: PROBE });
  return { result, sandbox, delivery };
}

function failureOf(run: Awaited<ReturnType<typeof outcome>>): unknown {
  try {
    measuredFrom(run.result, run.sandbox, { format: "glb" }, run.delivery, () => undefined);
  } catch (error) {
    if (error instanceof StageFailure) return error.failure;
    throw error;
  }
  return null;
}

describe("a limit of the machine in the one judge process", workBudget(240_000), () => {
  it("names a Blender that dies on a failed allocation a memory cap, not a crash", async () => {
    const run = await outcome("allocation");
    expect(run.result.interrupted).toMatchObject({ stage: "measure", failure: { stage: "measure", code: "memory_cap" } });
    expect(run.result.interrupted!.failure.message).toContain("ran out of memory under the 4096 MB cap");
  });

  it("names a MemoryError inside the measure stage a memory cap", async () => {
    expect(failureOf(await outcome("python-memory"))).toMatchObject({ stage: "measure", code: "memory_cap" });
  });

  it("names a file lock past its bound a file lock, inside a stage and while writing a record", async () => {
    expect(failureOf(await outcome("lock"))).toMatchObject({ stage: "measure", code: "file_lock" });
    const writing = await outcome("lock-exit");
    expect(writing.result.interrupted).toMatchObject({ stage: "measure", failure: { stage: "measure", code: "file_lock" } });
    expect(writing.result.interrupted!.failure.message).toContain("progress.log");
  });

  it.runIf(process.platform === "win32")("turns a file that Windows keeps locked past the bound into a file lock, not a crash", async () => {
    const failure = failureOf(await outcome("held"));
    expect(failure).toMatchObject({ stage: "measure", code: "file_lock" });
    expect((failure as { message: string }).message).toContain('"measurements.json"');
  });

  it("refuses to write a measurement that is not a finite number", async () => {
    expect(failureOf(await outcome("nan"))).toMatchObject({ stage: "measure", code: "non_finite" });
  });
});

describe("the judge on a machine that hits a limit", workBudget(240_000), () => {
  it("gives no verdict when the measure stage runs out of time: an infrastructure error, infrastructure.json and no report", async () => {
    const outDir = freshDir("infrastructure", "measure-timeout");
    const judged = judge({ specPath: writeSpec(specs, "measure-timeout"), assetPath: asset, outDir, timeoutMs: 1, preview: true });
    await expect(judged).rejects.toMatchObject({ name: "InfrastructureError", code: "timeout" });
    expect(JSON.parse(readFileSync(join(outDir, INFRASTRUCTURE_FILE), "utf8"))).toMatchObject({ verdict: null, infrastructure: true, code: "timeout" });
    expect(existsSync(join(outDir, "report.json"))).toBe(false);
  });

  it("stops an asset judge that runs past its total limit with error, which means judge again", () => {
    const root = freshDir("infrastructure", "entry");
    const blendworks = join(root, "blendworks");
    mkdirSync(join(blendworks, "dist", "judge"), { recursive: true });
    writeFileSync(join(blendworks, "dist", "judge", "cli.js"), "setTimeout(() => undefined, 600000);\n");
    for (const name of ["work", "spec"]) mkdirSync(join(root, "judge", name), { recursive: true });
    writeFileSync(join(root, "judge", "work", "crate.glb"), readFileSync(asset));
    writeFileSync(join(root, "judge", "spec", "spec.json"), JSON.stringify({ format: "glb" }));
    const layout = { ...layoutFrom({ BLENDWORKS_INPUT_ROOT: join(root, "judge"), BLENDWORKS_SCRATCH: join(root, "scratch"), BLENDWORKS_HOME: blendworks }) };
    const env = { ...process.env, BLENDWORKS_ASSET_SECONDS: "1" };
    const entry = judgeAsset({ layout, spec: join(root, "judge", "spec", "spec.json"), artifact: join(root, "judge", "work", "crate.glb"), commit: null, isolation: "test", env });
    expect(entry).toMatchObject({ verdict: "error", exitCode: 75 });
    expect(entry.reason).toContain("not a verdict");
  });
});
