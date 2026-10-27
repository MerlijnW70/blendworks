import { copyFileSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, extname, join, resolve } from "node:path";
import { blenderPath } from "../blender.js";
import type { z } from "zod";
import { copyDelivery, DeliveryError } from "./delivery.js";
import { describeDevice, type DeviceMode, type RenderDevice } from "./device.js";
import { closeupsOutputSchema } from "./measurements.js";
import { isolationText } from "./report.js";
import { detectTools, type Isolation, type Tools } from "./sandbox.js";
import { checkAsset, checkBlender, DEFAULT_BACKENDS, DEFAULTS, deviceMode, onDevice, runScript, seconds, StageFailure, workOut, type Attempt, type Sandbox } from "./stages.js";

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

type CloseupsOutput = Extract<z.infer<typeof closeupsOutputSchema>, { ok: true }>;

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

export async function closeups(options: CloseupsOptions): Promise<CloseupsResult> {
  const started = performance.now();
  const outDir = resolve(options.outDir);
  const assetPath = resolve(options.assetPath);
  const resolution = options.resolution ?? CLOSEUP_DEFAULTS.resolution;
  const samples = options.samples ?? CLOSEUP_DEFAULTS.samples;
  if (resolution > CLOSEUP_DEFAULTS.maxResolution || samples > CLOSEUP_DEFAULTS.maxSamples) {
    throw new StageFailure({ stage: "closeups", code: "usage", message: `--res and --samples are at most ${CLOSEUP_DEFAULTS.maxResolution}` });
  }
  const samplePixels = closeupSamplePixels(resolution, samples);
  if (samplePixels > CLOSEUP_DEFAULTS.maxSamplePixels) {
    throw new StageFailure({ stage: "closeups", code: "over_budget", message: `${CLOSEUP_NAMES.length} close-ups at ${resolution} px and ${samples} samples are ${samplePixels} sample-pixels, over the render budget of ${CLOSEUP_DEFAULTS.maxSamplePixels}` });
  }
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
    const out = workOut(sandbox);
    mkdirSync(out, { recursive: true });
    const args = [delivered, out, "--res", String(resolution), "--samples", String(samples), "--title", options.title ?? basename(assetPath)];
    args.push("--max-triangles", String(options.maxTriangles ?? DEFAULTS.maxTriangles));
    const outputPath = join(out, "closeups.json");
    let failedGpuSeconds: number | null = null;
    const chosen = await onDevice(mode, options.backends ?? DEFAULT_BACKENDS, async (request): Promise<Attempt<{ output: CloseupsOutput; isolation: Isolation }>> => {
      const run = await runScript("closeups", "closeups.py", [...args, "--device", request.device, "--backends", request.backends.join(",")], outputPath, sandbox, request.sandbox);
      const parsed = closeupsOutputSchema.safeParse(run.output);
      if (!parsed.success) throw new StageFailure({ stage: "closeups", code: "malformed", message: "the close-up script wrote malformed output" });
      const output = parsed.data;
      if (output.ok) return { ok: true, value: { output, isolation: run.isolation }, backend: output.device.backend, probes: output.probes };
      if (output.error.code === "gpu_unavailable" && request.sandbox === "gpu") {
        failedGpuSeconds = run.seconds;
        return { ok: false, message: output.error.message, probes: output.probes ?? [] };
      }
      throw new StageFailure({ stage: "closeups", ...output.error });
    });
    const { output, isolation } = chosen.value;
    for (const name of [...output.images.map((image) => basename(image.path)), CLOSEUP_SHEET, "closeups.json"]) {
      if (existsSync(join(out, name))) copyFileSync(join(out, name), join(outDir, name));
    }
    return {
      images: output.images.map((image) => ({ name: image.name, path: join(outDir, basename(image.path)) })),
      sheet: join(outDir, CLOSEUP_SHEET),
      device: chosen.device,
      sandbox: isolation,
      timings: { device: output.timings.device ?? failedGpuSeconds, render: output.timings.render, sheet: output.timings.sheet, total: seconds(performance.now() - started) },
    };
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

export function closeupSamplePixels(resolution: number, samples: number): number {
  return CLOSEUP_NAMES.length * resolution * resolution * samples;
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
