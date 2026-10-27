import { basename, join } from "node:path";
import type { z } from "zod";
import type { BackendProbe, DeviceMode } from "./device.js";
import { sheetOutputSchema, viewsOutputSchema, type Measurements } from "./measurements.js";
import { passOutput, type PassResult, type PassStage } from "./onepass.js";
import type { Failure, Report, RenderBudget, Renders } from "./report.js";
import { JUDGE_RENDER } from "./render-profile.js";
import { fallBack, pickDevice, seconds, sha256, StageFailure, type Sandbox } from "./stages.js";

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
type ViewsOutput = Extract<z.infer<typeof viewsOutputSchema>, { ok: true }>;
type SheetOutput = Extract<z.infer<typeof sheetOutputSchema>, { ok: true }>;

export type RenderAttempt = { result: PassResult; sandbox: Sandbox; gpu: boolean; fallback: boolean };

export type RenderPlan = { skipped: string | null; budget: RenderBudget };

export type RenderContinuation = (stages: PassStage[], gpu: boolean) => Promise<RenderAttempt>;

export function renderBudget(triangles: number | null, views: number, options: RenderOptions): RenderBudget {
  return {
    triangles: triangles ?? 0,
    samplePixels: views * RENDER_RESOLUTION * RENDER_RESOLUTION * RENDER_SAMPLES,
    maxTriangles: options.renderMaxTriangles ?? RENDER_BUDGET.maxTriangles,
    maxSamplePixels: RENDER_BUDGET.maxSamplePixels,
  };
}

export function overBudget(budget: RenderBudget): string | null {
  if (budget.triangles > budget.maxTriangles) return `over the render budget: ${budget.triangles} triangles, at most ${budget.maxTriangles}`;
  if (budget.samplePixels > budget.maxSamplePixels) return `over the render budget: ${budget.samplePixels} sample-pixels, at most ${budget.maxSamplePixels}`;
  return null;
}

export function samplesOverBudget(views: number, options: RenderOptions): boolean {
  const budget = renderBudget(null, views, options);
  return budget.samplePixels > budget.maxSamplePixels;
}

function emptyRenders(budget: RenderBudget): Renders {
  return { status: "failed", reason: null, failure: null, viewsSkipped: true, views: [], contactSheet: null, contactSheetSha256: null, budget };
}

function interruptedIn(attempt: RenderAttempt, stages: readonly PassStage[]): Failure | null {
  const interrupted = attempt.result.interrupted;
  return interrupted !== null && stages.includes(interrupted.stage) ? interrupted.failure : null;
}

export function sheetResult(attempt: RenderAttempt): SheetOutput {
  const failure = interruptedIn(attempt, ["sheet"]);
  if (failure !== null) throw new StageFailure(failure);
  const parsed = sheetOutputSchema.safeParse(passOutput(attempt.sandbox, "sheet"));
  if (!parsed.success) throw new StageFailure({ stage: "render", code: "malformed", message: "the render script wrote malformed output" });
  if (!parsed.data.ok) throw new StageFailure({ stage: "render", ...parsed.data.error });
  return parsed.data;
}

type ViewsVerdict = { kind: "rendered"; output: ViewsOutput } | { kind: "cpu"; reason: string; probes: BackendProbe[]; seconds: number | null };

function viewsResult(attempt: RenderAttempt, mode: DeviceMode): ViewsVerdict {
  const failure = interruptedIn(attempt, ["views", "sheet"]);
  if (failure !== null) {
    if (failure.code === "crashed" && attempt.gpu && mode === "auto") return { kind: "cpu", reason: failure.message, probes: [{ backend: "GPU sandbox", devices: [], usable: false, reason: failure.message }], seconds: null };
    throw new StageFailure(failure);
  }
  const parsed = viewsOutputSchema.safeParse(passOutput(attempt.sandbox, "views"));
  if (!parsed.success) throw new StageFailure({ stage: "render", code: "malformed", message: "the render script wrote malformed output" });
  const output = parsed.data;
  if (output.ok) return { kind: "rendered", output };
  if (output.error.code === "gpu_unavailable" && attempt.gpu) return { kind: "cpu", reason: output.error.message, probes: output.probes ?? [], seconds: output.probeSeconds ?? null };
  throw new StageFailure({ stage: "render", ...output.error });
}

export async function interpretRenders(draft: Draft, plan: RenderPlan, first: RenderAttempt, mode: DeviceMode, continueWith: RenderContinuation, outDir: string): Promise<RenderAttempt | null> {
  const renders = emptyRenders(plan.budget);
  draft.renders = renders;
  let failedGpuSeconds: number | null = null;
  let attempt = first;
  let sheet: SheetOutput | null = null;
  let views: ViewsOutput | null = null;
  try {
    if (plan.skipped !== null) {
      Object.assign(renders, { status: plan.skipped === "preview" ? "preview" : "skipped", reason: plan.skipped });
      draft.renderSandbox = attempt.result.isolation;
      sheet = sheetResult(attempt);
    } else {
      let verdict = viewsResult(attempt, mode);
      if (verdict.kind === "cpu") {
        failedGpuSeconds = verdict.seconds;
        const chosen = pickDevice(mode, verdict.probes);
        const device = chosen.kind === "gpu" ? fallBack(chosen, verdict.reason) : chosen;
        attempt = await continueWith(["views", "sheet"], false);
        verdict = viewsResult(attempt, mode);
        if (verdict.kind !== "rendered") throw new StageFailure({ stage: "device", code: "no_gpu", message: verdict.reason });
        draft.device = device;
      } else if (mode === "cpu") {
        draft.device = pickDevice(mode, []);
      } else {
        const device = pickDevice(mode, verdict.output.probes);
        const backend = verdict.output.device.backend;
        if (device.kind !== "gpu" || device.backend !== backend) {
          throw new StageFailure({ stage: "device", code: "inconsistent", message: `Blender rendered on ${backend}, but the probes choose ${device.backend ?? "the CPU"}` });
        }
        draft.device = device;
      }
      draft.renderSandbox = attempt.result.isolation;
      views = verdict.output;
      sheet = sheetResult(attempt);
      Object.assign(renders, { status: "rendered", viewsSkipped: false });
      draft.timings.device = views.timings.device ?? failedGpuSeconds;
      draft.timings.render = views.timings.views;
    }
    draft.timings.sheet = sheet.timings.sheet;
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    Object.assign(renders, { status: "failed", reason: error.failure.message, failure: error.failure, viewsSkipped: true });
    draft.timings.device ??= failedGpuSeconds;
    views = null;
    sheet = await recoverSheet(attempt, continueWith);
    if (sheet !== null) draft.timings.sheet = sheet.timings.sheet;
  }
  if (sheet === null) return null;
  renders.views = (views?.views ?? []).map((entry) => ({ view: entry.view, path: join(outDir, "views", basename(entry.path)), sha256: "" }));
  renders.contactSheet = join(outDir, "contact-sheet.png");
  return views === null ? null : attempt;
}

async function recoverSheet(attempt: RenderAttempt, continueWith: RenderContinuation): Promise<SheetOutput | null> {
  try {
    const drawn = sheetResult(attempt);
    if (drawn.preview) return drawn;
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
  }
  try {
    return sheetResult(await continueWith(["sheet"], false));
  } catch (error) {
    if (error instanceof StageFailure) return null;
    throw error;
  }
}

export function hashRenders(renders: Renders | null): void {
  if (renders === null) return;
  for (const view of renders.views) view.sha256 = sha256(view.path);
  if (renders.contactSheet !== null) renders.contactSheetSha256 = sha256(renders.contactSheet);
}
