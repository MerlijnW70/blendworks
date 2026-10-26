import { existsSync, mkdirSync, mkdtempSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { blenderPath } from "../blender.js";
import type { z } from "zod";
import type { DeviceMode } from "./device.js";
import { measureOutputSchema, renderOutputSchema, type Measurements } from "./measurements.js";
import { summarize, type Report, type Timings } from "./report.js";
import { evaluateRules } from "./rules.js";
import { detectTools, type Limits, type SandboxDevice, type Tools } from "./sandbox.js";
import { DEFAULT_VIEWS, readSpec, SpecError, type AssetSpec } from "./spec.js";
import { checkAsset, checkBlender, DEFAULT_BACKENDS, DEFAULTS, deviceMode, onDevice, runScript, seconds, sha256, StageFailure, type Attempt, type Sandbox } from "./stages.js";

export { DEFAULTS, SCRIPTS_DIR } from "./stages.js";

export type JudgeOptions = {
  specPath: string;
  assetPath: string;
  outDir: string;
  blender?: string;
  timeoutMs?: number;
  memoryBytes?: number;
  maxTriangles?: number;
  maxFileBytes?: number;
  tools?: Tools;
  preview?: boolean;
  device?: DeviceMode;
  backends?: readonly string[];
};

const OUTPUTS = ["report.json", "summary.txt", "measurements.json", "render.json", "contact-sheet.png", "views"];

function prepareOutDir(outDir: string): void {
  mkdirSync(outDir, { recursive: true });
  for (const name of OUTPUTS) rmSync(join(outDir, name), { recursive: true, force: true });
}

type Draft = Omit<Report, "summary">;

function uvGridPath(sandbox: Sandbox): string {
  return join(sandbox.workDir, "uv-grid.bin");
}

type RenderOutput = Extract<z.infer<typeof renderOutputSchema>, { ok: true }>;

async function renderStage(draft: Draft, spec: AssetSpec, assetPath: string, outDir: string, sandbox: Sandbox, maxTriangles: number, options: JudgeOptions) {
  const measurementsPath = join(outDir, "measurements.json");
  const views = (spec.views ?? DEFAULT_VIEWS).join(",");
  const title = spec.name ?? basename(assetPath);
  const baseArgs = [assetPath, measurementsPath, outDir, "--views", views, "--title", title, "--max-triangles", String(maxTriangles)];
  baseArgs.push("--uv-grid", uvGridPath(sandbox));
  const outputPath = join(outDir, "render.json");
  let failedGpuSeconds: number | null = null;
  const run = async (args: string[], device: SandboxDevice): Promise<Attempt<{ output: RenderOutput; seconds: number }>> => {
    const rendered = await runScript("render", "render.py", args, outputPath, sandbox, device);
    const parsed = renderOutputSchema.safeParse(rendered.output);
    if (!parsed.success) throw new StageFailure({ stage: "render", code: "malformed", message: "the render script wrote malformed output" });
    draft.renderSandbox = rendered.isolation;
    const output = parsed.data;
    if (output.ok) return { ok: true, value: { output, seconds: rendered.seconds }, backend: output.device?.backend ?? "CPU", probes: output.probes };
    if (output.error.code === "gpu_unavailable" && device === "gpu") {
      failedGpuSeconds = rendered.seconds;
      return { ok: false, message: output.error.message, probes: output.probes ?? [] };
    }
    throw new StageFailure({ stage: "render", ...output.error });
  };
  let result: { output: RenderOutput; seconds: number };
  if (options.preview === true) {
    const preview = await run([...baseArgs, "--mode", "preview"], "cpu");
    if (!preview.ok) throw new StageFailure({ stage: "render", code: "gpu_unavailable", message: preview.message });
    result = preview.value;
  } else {
    const chosen = await onDevice(deviceMode(options.device), options.backends ?? DEFAULT_BACKENDS, (request) =>
      run([...baseArgs, "--device", request.device, "--backends", request.backends.join(",")], request.sandbox),
    );
    draft.device = chosen.device;
    result = chosen.value;
  }
  const { output } = result;
  const probeSeconds = output.timings.device ?? failedGpuSeconds;
  draft.timings.device = probeSeconds;
  draft.timings.sheet = output.timings.sheet;
  draft.timings.render = options.preview === true ? null : Math.max(0, seconds((result.seconds - output.timings.sheet - (output.timings.device ?? 0)) * 1000));
  draft.renders = {
    viewsSkipped: options.preview === true,
    views: output.views.map((entry) => ({ view: entry.view, path: resolve(entry.path) })),
    contactSheet: join(outDir, "contact-sheet.png"),
  };
}

function emptyTimings(): Timings {
  return { measure: null, device: null, render: null, sheet: null, total: 0 };
}

export async function judge(options: JudgeOptions): Promise<Report> {
  const started = performance.now();
  const outDir = resolve(options.outDir);
  const specPath = resolve(options.specPath);
  const assetPath = resolve(options.assetPath);
  const limits: Limits = { timeoutMs: options.timeoutMs ?? DEFAULTS.timeoutMs, memoryBytes: options.memoryBytes ?? DEFAULTS.memoryBytes };
  const maxTriangles = options.maxTriangles ?? DEFAULTS.maxTriangles;
  prepareOutDir(outDir);
  const draft: Draft = {
    passed: false,
    preview: options.preview === true,
    spec: { path: specPath, sha256: existsSync(specPath) && statSync(specPath).isFile() ? sha256(specPath) : null, name: null },
    asset: { path: assetPath, sha256: null, bytes: null },
    blender: null,
    sandbox: null,
    renderSandbox: null,
    device: null,
    failure: null,
    rules: [],
    measurements: null,
    renders: null,
    timings: emptyTimings(),
  };
  const workDir = mkdtempSync(join(tmpdir(), "blendworks-judge-"));
  try {
    let spec: AssetSpec;
    try {
      spec = readSpec(specPath);
    } catch (error) {
      if (error instanceof SpecError) throw new StageFailure({ stage: "spec", code: "invalid_spec", message: error.problems.join("; ") });
      throw error;
    }
    draft.spec.name = spec.name ?? null;
    draft.asset.bytes = checkAsset(assetPath, options.maxFileBytes ?? DEFAULTS.maxFileBytes);
    draft.asset.sha256 = sha256(assetPath);
    const blender = options.blender ?? blenderPath();
    draft.blender = await checkBlender(blender);
    if (options.preview !== true) deviceMode(options.device);
    const sandbox: Sandbox = { blender, limits, tools: options.tools ?? detectTools(), workDir };
    const measurementsPath = join(outDir, "measurements.json");
    const measureArgs = [assetPath, measurementsPath, "--max-triangles", String(maxTriangles), "--uv-grid", uvGridPath(sandbox)];
    const measured = await runScript("measure", "measure.py", measureArgs, measurementsPath, sandbox);
    draft.sandbox = measured.isolation;
    draft.timings.measure = measured.seconds;
    const parsed = measureOutputSchema.safeParse(measured.output);
    if (!parsed.success) throw new StageFailure({ stage: "measure", code: "malformed", message: "the measuring script wrote malformed output" });
    if (!parsed.data.ok) throw new StageFailure({ stage: "measure", ...parsed.data.error });
    const measurements: Measurements = parsed.data.measurements;
    draft.measurements = measurements;
    draft.rules = evaluateRules(spec, measurements);
    await renderStage(draft, spec, assetPath, outDir, sandbox, maxTriangles, options);
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    draft.failure = error.failure;
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
  if (draft.failure) draft.rules.unshift({ rule: draft.failure.stage, measured: draft.failure.message, limit: "to complete", pass: false });
  draft.passed = draft.failure === null && draft.rules.length > 0 && draft.rules.every((rule) => rule.pass);
  draft.timings.total = seconds(performance.now() - started);
  const report: Report = { ...draft, summary: summarize(draft) };
  writeFileSync(join(outDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  writeFileSync(join(outDir, "summary.txt"), `${report.summary}\n`);
  return report;
}
