import { cpSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { DeviceMode } from "../judge/device.js";
import { DEFAULT_BACKENDS, deviceMode, onDevice, StageFailure, workOut, type Attempt, type Sandbox } from "../judge/stages.js";
import type { SandboxDevice } from "../judge/sandbox.js";
import type { RenderDevice } from "../judge/device.js";
import type { LodsRule } from "../judge/spec.js";
import { lodsOutputSchema, packageRenderSchema, type PackageRender } from "./schemas.js";
import { runPackageScript } from "./stage.js";

export const PACKAGE_RENDER_BUDGET = { maxSamplePixels: 256 * 1024 * 1024, maxCrop: 512, samples: 16 };
export const DEFAULT_PACKAGE_VIEWS = ["front", "back", "left", "right", "top", "three-quarter"] as const;

export type LodsStage = Extract<ReturnType<typeof lodsOutputSchema.parse>, { ok: true }>;

export type StageOptions = { maxTriangles: number; device?: DeviceMode; backends?: readonly string[]; renderTimeoutMs?: number };

export function packageDir(sandbox: Sandbox): string {
  return join(workOut(sandbox), "package");
}

export function lodConfig(lods: LodsRule | undefined): Record<string, unknown> {
  if (lods === undefined) return { count: 0 };
  const config: Record<string, unknown> = { count: lods.count };
  if (lods.ratios !== undefined) config.ratios = lods.ratios;
  if (lods.maxScreenError !== undefined) config.maxScreenError = lods.maxScreenError;
  if (lods.distances !== undefined) config.distances = lods.distances;
  return config;
}

export async function lodsStage(assetPath: string, stem: string, lods: LodsRule | undefined, sandbox: Sandbox, options: StageOptions): Promise<LodsStage> {
  const folder = join(packageDir(sandbox), "lods");
  mkdirSync(folder, { recursive: true });
  const configPath = join(packageDir(sandbox), "lod-config.json");
  writeFileSync(configPath, JSON.stringify(lodConfig(lods)));
  const args = [assetPath, folder, "--config", configPath, "--layout", lods?.files ?? "single", "--stem", stem, "--max-triangles", String(options.maxTriangles)];
  const stage = await runPackageScript("package_lods.py", args, join(folder, "lods.json"), sandbox);
  const parsed = lodsOutputSchema.safeParse(stage.output);
  if (!parsed.success) throw new StageFailure({ stage: "package", code: "malformed", message: "the LOD script wrote malformed output" });
  if (!parsed.data.ok) throw new StageFailure({ stage: "package", ...parsed.data.error });
  return parsed.data;
}

export function renderBudgetSamplePixels(levels: number, views: number): number {
  return levels * views * 2 * PACKAGE_RENDER_BUDGET.maxCrop * PACKAGE_RENDER_BUDGET.maxCrop * PACKAGE_RENDER_BUDGET.samples;
}

export type RenderAttempt = { output: PackageRender; device: RenderDevice | null };

export async function renderStage(views: readonly string[], sandbox: Sandbox, options: StageOptions): Promise<RenderAttempt> {
  const base = join(packageDir(sandbox), "render");
  mkdirSync(base, { recursive: true });
  const lodsPath = join(packageDir(sandbox), "lods", "lods.json");
  const folder = join(packageDir(sandbox), "lods");
  const outputPath = join(base, "render.json");
  const baseArgs = [lodsPath, folder, base, "--views", views.join(","), "--samples", String(PACKAGE_RENDER_BUDGET.samples), "--max-triangles", String(options.maxTriangles)];
  const limits = { ...sandbox.limits, timeoutMs: options.renderTimeoutMs ?? sandbox.limits.timeoutMs };
  const run = async (args: string[], device: SandboxDevice): Promise<Attempt<PackageRender>> => {
    const rendered = await runPackageScript("package_render.py", args, outputPath, { ...sandbox, limits }, device);
    const parsed = packageRenderSchema.safeParse(rendered.output);
    if (!parsed.success) throw new StageFailure({ stage: "package", code: "malformed", message: "the LOD render script wrote malformed output" });
    const output = parsed.data;
    if (output.ok) return { ok: true, value: output, backend: output.device?.backend ?? "CPU", probes: output.probes };
    if (output.error.code === "gpu_unavailable" && device === "gpu") return { ok: false, message: output.error.message, probes: output.probes ?? [] };
    throw new StageFailure({ stage: "package", ...output.error });
  };
  if (views.length === 0) {
    const measured = await run([...baseArgs, "--device", "CPU"], "cpu");
    if (!measured.ok) throw new StageFailure({ stage: "package", code: "gpu_unavailable", message: measured.message });
    return { output: measured.value, device: null };
  }
  const chosen = await onDevice(deviceMode(options.device), options.backends ?? DEFAULT_BACKENDS, (request) =>
    run([...baseArgs, "--device", request.device, "--backends", request.backends.join(",")], request.sandbox),
  );
  return { output: chosen.value, device: chosen.device };
}

export function copyRenders(sandbox: Sandbox, outDir: string): void {
  const source = join(packageDir(sandbox), "render");
  mkdirSync(outDir, { recursive: true });
  for (const name of readdirSync(source)) if (name.endsWith(".png")) cpSync(join(source, name), join(outDir, name));
}
