import { basename } from "node:path";
import { closeupArgs, CLOSEUP_DEFAULTS, closeupRefusal } from "./closeups.js";
import type { Delivery } from "./delivery.js";
import type { DeviceMode } from "./device.js";
import { measureOutputSchema, measurementsSchema, type Measurements } from "./measurements.js";
import { motionExtras, withBoneScheme } from "./motion-rules.js";
import { naturalViewArgs } from "./natural.js";
import { naturalMeasureOptions, naturalMeasureParts, wantsNaturalSilhouettes } from "./natural-spec.js";
import { finishNatural } from "./natural-sets.js";
import { weightTolerance } from "./motion-spec.js";
import { wantsObjectList } from "./object-rules.js";
import { passOutput, type PassResult, type PassStage, type StageGroup } from "./onepass.js";
import { referencePassFrame, silhouetteArgs, type LoadedReference } from "./reference.js";
import { renderProfile } from "./render-profile.js";
import { RENDER_BUDGET, samplesOverBudget, type RenderOptions } from "./render-stage.js";
import { upAxis } from "./shape-rules.js";
import { DEFAULT_VIEWS, type AssetSpec } from "./spec.js";
import { DEFAULT_BACKENDS, seconds, StageFailure, type Sandbox } from "./stages.js";
import { floatingTolerance } from "./texture-rules.js";
import type { VisualOptions } from "./visual/stage.js";

export type PassPlan = {
  stages: PassStage[];
  args: string[];
  deviceArgs: string[];
  gpu: boolean;
  views: boolean;
  closeups: boolean;
  closeupRefusal: StageFailure | null;
  budgets: Record<StageGroup, number>;
};

export type PlanInput = {
  spec: AssetSpec;
  delivery: Delivery;
  references: LoadedReference[] | null;
  maxTriangles: number;
  timeoutMs: number;
  mode: DeviceMode | null;
  render: RenderOptions;
  visual: VisualOptions;
};

function measureArgs(spec: AssetSpec): string[] {
  const args: string[] = [];
  const tolerance = floatingTolerance(spec);
  if (tolerance !== undefined) args.push("--floating-tolerance", String(tolerance));
  if (wantsObjectList(spec)) args.push("--objects", "yes");
  const extras = motionExtras(spec);
  if (extras.length > 0) args.push("--extras", extras.join(","), "--weight-tolerance", String(weightTolerance(spec.skin)));
  const natural = naturalMeasureParts(spec.natural);
  if (natural.length > 0) args.push("--natural", natural.join(","), ...naturalMeasureOptions(spec.natural));
  return args;
}

function renderArgs(spec: AssetSpec, assetPath: string, renderMaxTriangles: number): string[] {
  const views = spec.views ?? DEFAULT_VIEWS;
  const profile = renderProfile();
  return ["--views", views.join(","), "--title", spec.name ?? basename(assetPath), "--res", String(profile.resolution), "--samples", String(profile.samples), "--render-max-triangles", String(renderMaxTriangles)];
}

export function deviceArgs(mode: DeviceMode | null, backends: readonly string[]): string[] {
  if (mode === null || mode === "cpu") return ["--device", "CPU"];
  return ["--device", "AUTO", "--backends", backends.join(","), "--gpu-fallback", mode === "auto" ? "yes" : "no"];
}

export function planPass(input: PlanInput): PassPlan {
  const { spec, render } = input;
  const viewCount = (spec.views ?? DEFAULT_VIEWS).length;
  const views = render.preview !== true && !samplesOverBudget(viewCount, render);
  const stages: PassStage[] = ["measure"];
  const args = ["--max-triangles", String(input.maxTriangles), "--visibility-seed", input.delivery.sha256, ...measureArgs(spec)];
  const references = spec.reference !== undefined && input.references !== null;
  if (references || wantsNaturalSilhouettes(spec.natural)) stages.push("reference");
  if (spec.reference !== undefined && input.references !== null) args.push(...silhouetteArgs(input.references, referencePassFrame(spec.reference, upAxis(spec))));
  args.push(...naturalViewArgs(spec.natural));
  if (views) stages.push("views");
  stages.push("sheet");
  args.push(...renderArgs(spec, input.delivery.main, render.renderMaxTriangles ?? RENDER_BUDGET.maxTriangles));
  const resolution = input.visual.closeupResolution ?? CLOSEUP_DEFAULTS.resolution;
  const samples = input.visual.closeupSamples ?? CLOSEUP_DEFAULTS.samples;
  const refusal = spec.visual === undefined ? null : closeupRefusal(resolution, samples);
  const closeups = spec.visual !== undefined && views && refusal === null;
  if (closeups) {
    stages.push("closeups");
    args.push(...closeupArgs(resolution, samples, spec.name ?? "asset"));
  }
  const renderTimeout = views ? (render.renderTimeoutMs ?? input.timeoutMs) : input.timeoutMs;
  return {
    stages,
    args,
    deviceArgs: views ? deviceArgs(input.mode, render.backends ?? DEFAULT_BACKENDS) : deviceArgs(null, []),
    gpu: views && input.mode !== null && input.mode !== "cpu",
    views,
    closeups,
    closeupRefusal: refusal,
    budgets: { measure: input.timeoutMs, reference: input.timeoutMs, render: renderTimeout, closeups: input.timeoutMs },
  };
}

function reported(spec: AssetSpec, measurements: Measurements): Measurements {
  if (spec.textures !== undefined) return measurements;
  const { textures: _, ...rest } = measurements;
  return rest;
}

export function measuredFrom(result: PassResult, sandbox: Sandbox, spec: AssetSpec, delivery: Delivery, onIsolation: (seconds: number | null) => void): Measurements {
  if (result.interrupted !== null && result.interrupted.stage === "measure") throw new StageFailure(result.interrupted.failure);
  const record = result.records.find((entry) => entry.stage === "measure");
  onIsolation(record === undefined ? null : seconds(record.endedAt - result.spawnedAt));
  const parsed = measureOutputSchema.safeParse(passOutput(sandbox, "measure"));
  if (!parsed.success) throw new StageFailure({ stage: "measure", code: "malformed", message: "the measuring script wrote malformed output" });
  if (!parsed.data.ok) throw new StageFailure({ stage: "measure", ...parsed.data.error });
  const { format, natural, ...rest } = parsed.data.measurements;
  const finished = finishNatural(natural);
  return withBoneScheme(spec, reported(spec, measurementsSchema.parse({ format, fileBytes: delivery.bytes, ...rest, ...(finished === undefined ? {} : { natural: finished }), references: delivery.references })));
}

export function stageSeconds(result: PassResult, stage: PassStage): number | null {
  const record = result.records.find((entry) => entry.stage === stage);
  return record === undefined ? null : record.seconds;
}
