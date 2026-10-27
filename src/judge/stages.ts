import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chooseDevice, DeviceError, deviceModeFromEnvironment, fallBackToCpu, GPU_BACKENDS, type BackendProbe, type DeviceMode, type RenderDevice } from "./device.js";
import type { Failure } from "./report.js";
import { planSandbox, runSandboxed, type Isolation, type Limits, type SandboxDevice, type Tools } from "./sandbox.js";
import { FORMATS } from "./spec.js";
import { blenderVersion, BlenderVersionError } from "./version.js";

export const SCRIPTS_DIR = fileURLToPath(new URL("../../bridge/judge/", import.meta.url));

const LOW_INTEGRITY_LAUNCH_FAILED = 120;

export const DEFAULTS = { timeoutMs: 300_000, memoryBytes: 4096 * 1024 * 1024, maxTriangles: 2_000_000, maxFileBytes: 256 * 1024 * 1024 };

export class StageFailure extends Error {
  constructor(readonly failure: Failure) {
    super(failure.message);
  }
}

export type Sandbox = { blender: string; limits: Limits; tools: Tools; workDir: string; delivery: string };

export function workOut(sandbox: Sandbox): string {
  return join(sandbox.workDir, "out");
}

export type StageResult = { output: unknown; isolation: Isolation; seconds: number };

export function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function seconds(milliseconds: number): number {
  return Math.round(milliseconds / 10) / 100;
}

export function checkAsset(assetPath: string, maxFileBytes: number): number {
  if (!existsSync(assetPath)) throw new StageFailure({ stage: "asset", code: "missing", message: "the asset file does not exist" });
  const stats = statSync(assetPath);
  if (!stats.isFile()) throw new StageFailure({ stage: "asset", code: "not_a_file", message: "the asset path is not a file" });
  if (stats.size === 0) throw new StageFailure({ stage: "asset", code: "empty", message: "the asset file is empty" });
  if (stats.size > maxFileBytes) {
    throw new StageFailure({ stage: "asset", code: "too_large", message: `the asset is ${stats.size} bytes, over the judge's cap of ${maxFileBytes}` });
  }
  const extension = extname(assetPath).slice(1).toLowerCase();
  if (!(FORMATS as readonly string[]).includes(extension)) {
    throw new StageFailure({ stage: "asset", code: "unsupported_format", message: `.${extension} is not a supported format (${FORMATS.join(", ")})` });
  }
  return stats.size;
}

export async function checkBlender(blender: string): Promise<string> {
  try {
    return await blenderVersion(blender);
  } catch (error) {
    if (error instanceof BlenderVersionError) throw new StageFailure({ stage: "blender", code: "unsupported_blender", message: error.message });
    throw error;
  }
}

function readOutput(path: string): unknown {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return undefined;
  }
}

export async function runScript(
  stage: Failure["stage"],
  script: string,
  scriptArgs: string[],
  outputPath: string,
  sandbox: Sandbox,
  device: SandboxDevice = "cpu",
): Promise<StageResult> {
  const { blender, limits, tools, workDir } = sandbox;
  const view = { workDir, writable: [workOut(sandbox)], readOnly: [SCRIPTS_DIR, sandbox.delivery] };
  const plan = planSandbox(blender, join(SCRIPTS_DIR, script), scriptArgs, limits, tools, device, view);
  const started = performance.now();
  const result = await runSandboxed(plan, workDir);
  const elapsed = seconds(performance.now() - started);
  if (result.timedOut) {
    throw new StageFailure({ stage, code: "timeout", message: `Blender took longer than ${limits.timeoutMs / 1000} s and was stopped` });
  }
  const output = readOutput(outputPath);
  if (output === undefined && result.code === LOW_INTEGRITY_LAUNCH_FAILED && plan.lowIntegrity) {
    throw new StageFailure({ stage, code: "sandbox", message: `the low-integrity launcher could not start Blender: ${result.output.trim().slice(-300)}` });
  }
  if (output === undefined) {
    const tail = result.output.trim().split("\n").slice(-3).join(" | ").slice(0, 400);
    throw new StageFailure({
      stage,
      code: "crashed",
      message: `Blender exited with code ${result.code ?? result.signal} without a result (out of memory under the ${limits.memoryBytes / 1048576} MB cap, or a crash): ${tail}`,
    });
  }
  return { output, isolation: plan.isolation, seconds: elapsed };
}

export function deviceMode(requested: DeviceMode | undefined): DeviceMode {
  if (requested !== undefined) return requested;
  try {
    return deviceModeFromEnvironment();
  } catch (error) {
    if (error instanceof DeviceError) throw new StageFailure({ stage: "device", code: "invalid_device", message: error.message });
    throw error;
  }
}

export function pickDevice(mode: DeviceMode, probes: BackendProbe[]): RenderDevice {
  try {
    return chooseDevice(mode, probes);
  } catch (error) {
    if (error instanceof DeviceError) throw new StageFailure({ stage: "device", code: "no_gpu", message: error.message });
    throw error;
  }
}

export function fallBack(device: RenderDevice, reason: string): RenderDevice {
  try {
    return fallBackToCpu(device, reason);
  } catch (error) {
    if (error instanceof DeviceError) throw new StageFailure({ stage: "device", code: "no_gpu", message: error.message });
    throw error;
  }
}

export type DeviceRequest = { device: "AUTO" | "CPU"; backends: string[]; sandbox: SandboxDevice };

export type Attempt<T> =
  | { ok: true; value: T; backend: string; probes: BackendProbe[] }
  | { ok: false; message: string; probes: BackendProbe[] };

export async function onDevice<T>(
  mode: DeviceMode,
  backends: readonly string[],
  attempt: (request: DeviceRequest) => Promise<Attempt<T>>,
): Promise<{ device: RenderDevice; value: T }> {
  const onCpu = async (device: RenderDevice) => {
    const result = await attempt({ device: "CPU", backends: [], sandbox: "cpu" });
    if (!result.ok) throw new StageFailure({ stage: "device", code: "no_gpu", message: result.message });
    return { device, value: result.value };
  };
  if (mode === "cpu") return onCpu(pickDevice(mode, []));
  let first: Attempt<T>;
  try {
    first = await attempt({ device: "AUTO", backends: [...backends], sandbox: "gpu" });
  } catch (error) {
    if (!(error instanceof StageFailure) || error.failure.code !== "crashed" || mode !== "auto") throw error;
    return onCpu(pickDevice(mode, [{ backend: "GPU sandbox", devices: [], usable: false, reason: error.failure.message }]));
  }
  if (first.ok) {
    const device = pickDevice(mode, first.probes);
    if (device.kind !== "gpu" || device.backend !== first.backend) {
      throw new StageFailure({ stage: "device", code: "inconsistent", message: `Blender rendered on ${first.backend}, but the probes choose ${device.backend ?? "the CPU"}` });
    }
    return { device, value: first.value };
  }
  const chosen = pickDevice(mode, first.probes);
  return onCpu(chosen.kind === "gpu" ? fallBack(chosen, first.message) : chosen);
}

export const DEFAULT_BACKENDS: readonly string[] = GPU_BACKENDS;
