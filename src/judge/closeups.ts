import { copyFileSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, extname, join, resolve } from "node:path";
import { blenderPath } from "../blender.js";
import type { z } from "zod";
import { copyDelivery, DeliveryError } from "./delivery.js";
import { describeDevice, type DeviceMode, type RenderDevice } from "./device.js";
import { closeupsOutputSchema } from "./measurements.js";
import { warmKernels } from "./gpu-cache.js";
import { withSharedAccess } from "./shared-access.js";
import { passOutput, PASS_OUTPUTS, runPass, type PassResult } from "./onepass.js";
import { isolationText } from "./report.js";
import { detectTools, type Isolation, type Tools } from "./sandbox.js";
import { checkAsset, checkBlender, DEFAULT_BACKENDS, DEFAULTS, deviceMode, onDevice, seconds, StageFailure, workOut, type Attempt, type Sandbox } from "./stages.js";

export const CLOSEUP_DEFAULTS = { resolution: 1200, samples: 16, timeoutMs: 900_000, maxResolution: 4096, maxSamples: 4096, maxSamplePixels: 1_500_000_000 };

const ANGLES = ["front-right", "back-left"];
const QUADRANTS = ["top-left", "top-right", "bottom-left", "bottom-right"];
export const CLOSEUP_NAMES = ["hero", ...ANGLES.flatMap((angle) => QUADRANTS.map((quadrant) => `${angle}-${quadrant}`))];
export const CLOSEUP_SHEET = "closeup-sheet.png";

export type CloseupsOptions = {
  assetPath: string;
  outDir: string;
  resolution?: number;
  samples?: number;
  title?: string;
  blender?: string;
  timeoutMs?: number;
  memoryBytes?: number;
  maxTriangles?: number;
  maxFileBytes?: number;
  tools?: Tools;
  device?: DeviceMode;
  backends?: readonly string[];
};

export type CloseupsOutput = Extract<z.infer<typeof closeupsOutputSchema>, { ok: true }>;

export type CloseupsResult = {
  images: { name: string; path: string }[];
  sheet: string;
  device: RenderDevice;
  sandbox: Isolation;
  timings: { device: number | null; render: number; sheet: number; total: number };
};

function prepareOutDir(outDir: string): void {
  mkdirSync(outDir, { recursive: true });
  for (const name of [...CLOSEUP_NAMES.map((image) => `${image}.png`), CLOSEUP_SHEET, "closeups.json"]) rmSync(join(outDir, name), { force: true });
}

export function closeupSamplePixels(resolution: number, samples: number): number {
  return CLOSEUP_NAMES.length * resolution * resolution * samples;
}

export function closeupRefusal(resolution: number, samples: number): StageFailure | null {
  if (resolution > CLOSEUP_DEFAULTS.maxResolution || samples > CLOSEUP_DEFAULTS.maxSamples) {
    return new StageFailure({ stage: "closeups", code: "usage", message: `--res and --samples are at most ${CLOSEUP_DEFAULTS.maxResolution}` });
  }
  const samplePixels = closeupSamplePixels(resolution, samples);
  if (samplePixels > CLOSEUP_DEFAULTS.maxSamplePixels) {
    return new StageFailure({ stage: "closeups", code: "over_budget", message: `${CLOSEUP_NAMES.length} close-ups at ${resolution} px and ${samples} samples are ${samplePixels} sample-pixels, over the render budget of ${CLOSEUP_DEFAULTS.maxSamplePixels}` });
  }
  return null;
}

export function closeupArgs(resolution: number, samples: number, title: string): string[] {
  return ["--closeup-res", String(resolution), "--closeup-samples", String(samples), "--closeup-title", title];
}

export type CloseupsAttempt = Attempt<{ output: CloseupsOutput; isolation: Isolation; seconds: number }>;

export function closeupsAttempt(result: PassResult, sandbox: Sandbox, gpu: boolean): CloseupsAttempt {
  if (result.interrupted !== null && result.interrupted.stage === "closeups") throw new StageFailure({ ...result.interrupted.failure, stage: "closeups" });
  const parsed = closeupsOutputSchema.safeParse(passOutput(sandbox, "closeups"));
  if (!parsed.success) throw new StageFailure({ stage: "closeups", code: "malformed", message: "the close-up script wrote malformed output" });
  const output = parsed.data;
  const record = result.records.find((entry) => entry.stage === "closeups");
  if (output.ok) return { ok: true, value: { output, isolation: result.isolation, seconds: record?.seconds ?? 0 }, backend: output.device.backend, probes: output.probes };
  if (output.error.code === "gpu_unavailable" && gpu) return { ok: false, message: output.error.message, probes: output.probes ?? [] };
  throw new StageFailure({ stage: "closeups", ...output.error });
}

export function copyCloseups(sandbox: Sandbox, output: CloseupsOutput, outDir: string): { name: string; path: string }[] {
  mkdirSync(outDir, { recursive: true });
  const folder = dirname(join(workOut(sandbox), PASS_OUTPUTS.closeups));
  for (const name of [...output.images.map((image) => basename(image.path)), CLOSEUP_SHEET, "closeups.json"]) {
    if (existsSync(join(folder, name))) withSharedAccess(() => copyFileSync(join(folder, name), join(outDir, name)));
  }
  return output.images.map((image) => ({ name: image.name, path: join(outDir, basename(image.path)) }));
}

export async function closeups(options: CloseupsOptions): Promise<CloseupsResult> {
  const started = performance.now();
  const outDir = resolve(options.outDir);
  const assetPath = resolve(options.assetPath);
  const resolution = options.resolution ?? CLOSEUP_DEFAULTS.resolution;
  const samples = options.samples ?? CLOSEUP_DEFAULTS.samples;
  const refusal = closeupRefusal(resolution, samples);
  if (refusal !== null) throw refusal;
  const maxFileBytes = options.maxFileBytes ?? DEFAULTS.maxFileBytes;
  checkAsset(assetPath, maxFileBytes);
  const blender = options.blender ?? blenderPath();
  await checkBlender(blender);
  const mode = deviceMode(options.device);
  prepareOutDir(outDir);
  const workDir = mkdtempSync(join(tmpdir(), "blendworks-closeups-"));
  try {
    const limits = { timeoutMs: options.timeoutMs ?? CLOSEUP_DEFAULTS.timeoutMs, memoryBytes: options.memoryBytes ?? DEFAULTS.memoryBytes };
    let delivered: string;
    let deliveryFolder: string;
    try {
      ({ main: delivered, folder: deliveryFolder } = copyDelivery(assetPath, extname(assetPath).slice(1).toLowerCase(), workDir, maxFileBytes));
    } catch (error) {
      if (error instanceof DeliveryError) throw new StageFailure({ stage: "asset", code: error.code, message: error.message });
      throw error;
    }
    const sandbox: Sandbox = { blender, limits, tools: options.tools ?? detectTools(blender), workDir, delivery: deliveryFolder };
    mkdirSync(workOut(sandbox), { recursive: true });
    const args = [...closeupArgs(resolution, samples, options.title ?? basename(assetPath)), "--max-triangles", String(options.maxTriangles ?? DEFAULTS.maxTriangles)];
    const budgets = { measure: limits.timeoutMs, reference: limits.timeoutMs, render: limits.timeoutMs, closeups: limits.timeoutMs };
    const chosen = await onDevice(mode, options.backends ?? DEFAULT_BACKENDS, async (request) => {
      const gpu = request.sandbox === "gpu";
      if (gpu) await warmKernels(sandbox, request.backends);
      const result = await runPass({ asset: delivered, stages: ["closeups"], args: [...args, "--device", request.device, "--backends", request.backends.join(",")], device: request.sandbox, sandbox, budgets, addressSpaceUntilGpu: gpu });
      return closeupsAttempt(result, sandbox, gpu);
    });
    const { output, isolation } = chosen.value;
    return {
      images: copyCloseups(sandbox, output, outDir),
      sheet: join(outDir, CLOSEUP_SHEET),
      device: chosen.device,
      sandbox: isolation,
      timings: { device: output.timings.device, render: output.timings.render, sheet: output.timings.sheet, total: seconds(performance.now() - started) },
    };
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

export function closeupsSummary(result: CloseupsResult): string {
  const { timings } = result;
  const stages = [timings.device === null ? null : `device ${timings.device.toFixed(2)} s`, `render ${timings.render.toFixed(2)} s`, `sheet ${timings.sheet.toFixed(2)} s`];
  return [
    `close-ups: ${result.images.length} images in ${dirname(result.sheet)}`,
    `  sheet: ${result.sheet}`,
    `  render: ${describeDevice(result.device)}`,
    `  sandbox: ${isolationText(result.sandbox)}`,
    `  time: ${stages.filter((stage) => stage !== null).join(", ")}, total ${timings.total.toFixed(2)} s`,
  ].join("\n");
}
