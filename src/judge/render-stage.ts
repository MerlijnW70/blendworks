import { basename, join } from "node:path";
import type { z } from "zod";
import type { DeviceMode } from "./device.js";
import { renderOutputSchema, type Measurements } from "./measurements.js";
import type { Report, RenderBudget, Renders } from "./report.js";
import type { SandboxDevice } from "./sandbox.js";
import { JUDGE_RENDER, renderProfile } from "./render-profile.js";
import { DEFAULT_VIEWS, type AssetSpec } from "./spec.js";
import { DEFAULT_BACKENDS, deviceMode, onDevice, runScript, seconds, sha256, StageFailure, workOut, type Attempt, type Sandbox } from "./stages.js";

export const RENDER_RESOLUTION = JUDGE_RENDER.resolution;
export const RENDER_SAMPLES = JUDGE_RENDER.samples;
export const RENDER_BUDGET = { maxTriangles: 2_000_000, maxSamplePixels: 64 * 1024 * 1024 };

export type RenderOptions = {
  preview?: boolean;
  device?: DeviceMode;
  backends?: readonly string[];
  renderTimeoutMs?: number;
  renderMaxTriangles?: number;
};

type Draft = Omit<Report, "summary">;
type RenderOutput = Extract<z.infer<typeof renderOutputSchema>, { ok: true }>;

export function uvGridPath(sandbox: Sandbox): string {
  return join(workOut(sandbox), "uv-grid.bin");
}

export function renderBudget(measurements: Measurements, views: number, options: RenderOptions): RenderBudget {
  return {
    triangles: measurements.triangles,
    samplePixels: views * RENDER_RESOLUTION * RENDER_RESOLUTION * RENDER_SAMPLES,
    maxTriangles: options.renderMaxTriangles ?? RENDER_BUDGET.maxTriangles,
    maxSamplePixels: RENDER_BUDGET.maxSamplePixels,
  };
}

function overBudget(budget: RenderBudget): string | null {
  if (budget.triangles > budget.maxTriangles) return `over the render budget: ${budget.triangles} triangles, at most ${budget.maxTriangles}`;
  if (budget.samplePixels > budget.maxSamplePixels) return `over the render budget: ${budget.samplePixels} sample-pixels, at most ${budget.maxSamplePixels}`;
  return null;
}

function emptyRenders(budget: RenderBudget): Renders {
  return { status: "failed", reason: null, failure: null, viewsSkipped: true, views: [], contactSheet: null, contactSheetSha256: null, budget };
}

export async function renderStage(draft: Draft, spec: AssetSpec, assetPath: string, outDir: string, sandbox: Sandbox, maxTriangles: number, options: RenderOptions): Promise<void> {
  const out = workOut(sandbox);
  const views = spec.views ?? DEFAULT_VIEWS;
  const budget = renderBudget(draft.measurements!, views.length, options);
  const renders = emptyRenders(budget);
  draft.renders = renders;
  const baseArgs = [assetPath, join(out, "measurements.json"), out, "--views", views.join(","), "--title", spec.name ?? basename(assetPath), "--max-triangles", String(maxTriangles)];
  baseArgs.push("--uv-grid", uvGridPath(sandbox));
  const profile = renderProfile();
  baseArgs.push("--res", String(profile.resolution), "--samples", String(profile.samples));
  const outputPath = join(out, "render.json");
  let failedGpuSeconds: number | null = null;
  const run = async (args: string[], device: SandboxDevice, target: Sandbox): Promise<Attempt<{ output: RenderOutput; seconds: number }>> => {
    const rendered = await runScript("render", "render.py", args, outputPath, target, device);
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
  const sheetOnly = async (): Promise<RenderOutput> => {
    const preview = await run([...baseArgs, "--mode", "preview"], "cpu", sandbox);
    if (!preview.ok) throw new StageFailure({ stage: "render", code: "gpu_unavailable", message: preview.message });
    draft.timings.sheet = preview.value.output.timings.sheet;
    return preview.value.output;
  };
  const skipped = options.preview === true ? "preview" : overBudget(budget);
  let output: RenderOutput | null = null;
  try {
    if (skipped !== null) {
      Object.assign(renders, { status: skipped === "preview" ? "preview" : "skipped", reason: skipped });
      output = await sheetOnly();
    } else {
      const limits = { ...sandbox.limits, timeoutMs: options.renderTimeoutMs ?? sandbox.limits.timeoutMs };
      const chosen = await onDevice(deviceMode(options.device), options.backends ?? DEFAULT_BACKENDS, (request) =>
        run([...baseArgs, "--device", request.device, "--backends", request.backends.join(",")], request.sandbox, { ...sandbox, limits }),
      );
      draft.device = chosen.device;
      output = chosen.value.output;
      const elapsed = chosen.value.seconds;
      Object.assign(renders, { status: "rendered", viewsSkipped: false });
      draft.timings.device = output.timings.device ?? failedGpuSeconds;
      draft.timings.sheet = output.timings.sheet;
      draft.timings.render = Math.max(0, seconds((elapsed - output.timings.sheet - (output.timings.device ?? 0)) * 1000));
    }
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    Object.assign(renders, { status: "failed", reason: error.failure.message, failure: error.failure, viewsSkipped: true });
    draft.timings.device ??= failedGpuSeconds;
    output = await sheetOnly().catch((sheetError: unknown) => {
      if (sheetError instanceof StageFailure) return null;
      throw sheetError;
    });
  }
  if (output === null) return;
  renders.views = output.views.map((entry) => {
    const path = join(outDir, "views", basename(entry.path));
    return { view: entry.view, path, sha256: "" };
  });
  renders.contactSheet = join(outDir, "contact-sheet.png");
}

export function hashRenders(renders: Renders | null): void {
  if (renders === null) return;
  for (const view of renders.views) view.sha256 = sha256(view.path);
  if (renders.contactSheet !== null) renders.contactSheetSha256 = sha256(renders.contactSheet);
}
