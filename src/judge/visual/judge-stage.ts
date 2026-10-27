import { join } from "node:path";
import { CLOSEUP_DEFAULTS, closeups } from "../closeups.js";
import type { DeviceMode } from "../device.js";
import type { Renders } from "../report.js";
import type { AssetSpec } from "../spec.js";
import { StageFailure, type Sandbox } from "../stages.js";
import type { EvidenceSource } from "./images.js";
import type { VisualRecord } from "./record.js";
import { inconclusive, scoreVisual, writeVisualRecord, type VisualOptions } from "./stage.js";

export const CLOSEUPS_FOLDER = "closeups";

export type VisualStageInput = {
  spec: AssetSpec;
  renders: Renders | null;
  assetPath: string;
  outDir: string;
  sandbox: Sandbox;
  maxTriangles: number;
  maxFileBytes: number;
  device?: DeviceMode;
  backends?: readonly string[];
  options: VisualOptions;
};

function viewSources(renders: Renders): EvidenceSource[] {
  return renders.views.map((view) => ({ name: view.view, kind: "view", path: view.path }));
}

async function closeupSources(input: VisualStageInput): Promise<EvidenceSource[]> {
  const result = await closeups({
    assetPath: input.assetPath,
    outDir: join(input.outDir, CLOSEUPS_FOLDER),
    resolution: input.options.closeupResolution ?? CLOSEUP_DEFAULTS.resolution,
    samples: input.options.closeupSamples ?? CLOSEUP_DEFAULTS.samples,
    title: input.spec.name ?? "asset",
    blender: input.sandbox.blender,
    timeoutMs: input.sandbox.limits.timeoutMs,
    memoryBytes: input.sandbox.limits.memoryBytes,
    maxTriangles: input.maxTriangles,
    maxFileBytes: input.maxFileBytes,
    tools: input.sandbox.tools,
    ...(input.device === undefined ? {} : { device: input.device }),
    ...(input.backends === undefined ? {} : { backends: input.backends }),
  });
  return result.images.map((image) => ({ name: image.name, kind: "closeup", path: image.path }));
}

export async function visualStage(input: VisualStageInput): Promise<VisualRecord> {
  const rule = input.spec.visual!;
  const env = input.options.env ?? process.env;
  let record: VisualRecord;
  const renders = input.renders;
  if (renders === null || renders.status !== "rendered" || renders.views.length === 0) {
    const status = renders?.status ?? "not rendered";
    record = inconclusive(rule, env, `the views did not render (${status}${renders?.reason ? `: ${renders.reason}` : ""}), so there is nothing to show the model`);
  } else {
    try {
      const sources = [...viewSources(renders), ...(await closeupSources(input))];
      record = await scoreVisual({ rule, brief: input.spec.brief ?? "", sources, outDir: input.outDir, options: input.options });
    } catch (error) {
      if (!(error instanceof Error)) throw error;
      const reason = error instanceof StageFailure ? `the close-ups failed: ${error.failure.message}` : `the visual judge could not run: ${error.message.split("\n")[0]}`;
      record = inconclusive(rule, env, reason);
    }
  }
  writeVisualRecord(input.outDir, record);
  return record;
}
