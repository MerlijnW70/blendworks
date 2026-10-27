import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { blenderPath } from "../blender.js";
import { closeupsAttempt, copyCloseups } from "./closeups.js";
import { copyDelivery, DeliveryError, type Delivery } from "./delivery.js";
import type { DeviceMode } from "./device.js";
import { renderRules } from "./integrity-rules.js";
import { deviceArgs, measuredFrom, planPass, stageSeconds, type PassPlan } from "./judge-pass.js";
import { runPass, type PassRequest, type PassResult, type PassStage } from "./onepass.js";
import { loadReferences, referenceStage, REFERENCE_FOLDER, silhouettesFrom, type LoadedReference } from "./reference.js";
import { hashRenders, interpretRenders, overBudget, renderBudget, type RenderAttempt } from "./render-stage.js";
import { summarize, type Report, type Timings } from "./report.js";
import { evaluateRules } from "./rules.js";
import { detectTools, type Limits, type Tools } from "./sandbox.js";
import { DEFAULT_VIEWS, readSpec, SpecError, type AssetSpec } from "./spec.js";
import { checkAsset, checkBlender, DEFAULT_BACKENDS, DEFAULTS, deviceMode, seconds, sha256, StageFailure, workOut, type Sandbox } from "./stages.js";
import { warmKernels } from "./gpu-cache.js";
import { withSharedAccess } from "./shared-access.js";
import { validatorRules } from "./texture-rules.js";
import { packageStage } from "../package/judge-stage.js";
import { wantsPackage } from "../package/rules.js";
import { validateGltf, ValidationError, VALIDATOR_DEFAULTS, type Validation } from "./validator.js";
import { CLOSEUPS_FOLDER, visualStage } from "./visual/judge-stage.js";
import { visualRules } from "./visual/record.js";
import type { VisualOptions } from "./visual/stage.js";

export { DEFAULTS, SCRIPTS_DIR } from "./stages.js";

export type JudgeOptions = {
  specPath: string;
  assetPath: string;
  outDir: string;
  blender?: string;
  timeoutMs?: number;
  renderTimeoutMs?: number;
  renderMaxTriangles?: number;
  memoryBytes?: number;
  maxTriangles?: number;
  maxFileBytes?: number;
  tools?: Tools;
  preview?: boolean;
  device?: DeviceMode;
  backends?: readonly string[];
  maxValidatorBytes?: number;
  afterCopy?: (delivery: Delivery) => void;
  afterPass?: (stages: PassStage[], result: PassResult) => void;
  visual?: VisualOptions;
};

const OUTPUTS = ["report.json", "summary.txt", "measurements.json", "validation.json", "render.json", "sheet.json", "contact-sheet.png", "views", "visual.json", "visual", "closeups", "package", REFERENCE_FOLDER];
const STAGE_OUTPUTS = ["measurements.json", "render.json", "sheet.json", "contact-sheet.png"];

function prepareOutDir(outDir: string): void {
  mkdirSync(outDir, { recursive: true });
  for (const name of OUTPUTS) rmSync(join(outDir, name), { recursive: true, force: true });
}

type Draft = Omit<Report, "summary">;

function writeJson(path: string, value: unknown): void {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

async function validationStage(draft: Draft, spec: AssetSpec, assetPath: string, outDir: string, options: JudgeOptions, timeoutMs: number): Promise<Validation | null> {
  const format = extname(assetPath).slice(1).toLowerCase();
  const wanted = spec.gltf !== undefined;
  if (wanted) draft.validation = null;
  if (format !== "glb" && format !== "gltf") return null;
  const limits = { maxBytes: options.maxValidatorBytes ?? VALIDATOR_DEFAULTS.maxBytes, heapMb: VALIDATOR_DEFAULTS.heapMb, timeoutMs };
  let validation: Validation;
  try {
    validation = await validateGltf(assetPath, format, limits);
  } catch (error) {
    if (!(error instanceof ValidationError)) throw error;
    writeJson(join(outDir, "validation.json"), { ok: false, error: { code: error.code, message: error.message } });
    if (wanted) throw new StageFailure({ stage: "validate", code: error.code, message: error.message });
    return null;
  }
  writeJson(join(outDir, "validation.json"), { ok: true, ...validation });
  if (wanted) {
    draft.validation = validation;
    draft.rules = validatorRules(spec, validation);
  }
  return validation;
}

function emptyTimings(): Timings {
  return { measure: null, device: null, render: null, sheet: null, total: 0 };
}

function deliver(draft: Draft, assetPath: string, format: string, workDir: string, maxFileBytes: number): Delivery {
  let delivery: Delivery;
  try {
    delivery = copyDelivery(assetPath, format, workDir, maxFileBytes);
  } catch (error) {
    if (error instanceof DeliveryError) throw new StageFailure({ stage: "asset", code: error.code, message: error.message });
    throw error;
  }
  const main = delivery.files.find((file) => file.path === basename(delivery.main));
  Object.assign(draft.asset, { sha256: main?.sha256 ?? null, bytes: main?.bytes ?? null, files: delivery.files, setSha256: delivery.sha256, setBytes: delivery.bytes });
  return delivery;
}

function collectOutputs(workDir: string, outDir: string, draft: Draft): void {
  const out = join(workDir, "out");
  for (const name of STAGE_OUTPUTS) if (existsSync(join(out, name))) withSharedAccess(() => copyFileSync(join(out, name), join(outDir, name)));
  const views = draft.renders?.views ?? [];
  if (views.length > 0) mkdirSync(join(outDir, "views"), { recursive: true });
  for (const view of views) withSharedAccess(() => cpSync(join(out, "views", basename(view.path)), view.path));
  if (draft.renders?.contactSheet && !existsSync(draft.renders.contactSheet)) draft.renders.contactSheet = null;
  hashRenders(draft.renders);
}

type Started = { version: string; asset: string; sandbox: Sandbox; plan: PassPlan; mode: DeviceMode | null; first: PassResult; run: (request: PassRequest) => Promise<PassResult> };

async function startBlender(spec: AssetSpec, delivery: Delivery, references: LoadedReference[] | null, workDir: string, limits: Limits, maxTriangles: number, options: JudgeOptions, signal: AbortSignal): Promise<Started> {
  const blender = options.blender ?? blenderPath();
  const version = await checkBlender(blender);
  const mode = options.preview === true ? null : deviceMode(options.device);
  const sandbox: Sandbox = { blender, limits, tools: options.tools ?? detectTools(blender), workDir, delivery: delivery.folder };
  mkdirSync(workOut(sandbox), { recursive: true });
  const render = { ...options, ...(options.preview === true ? { preview: true } : {}) };
  const plan = planPass({ spec, delivery, references, maxTriangles, timeoutMs: limits.timeoutMs, mode, render, visual: options.visual ?? {} });
  const run = async (request: PassRequest): Promise<PassResult> => {
    const result = await runPass(request);
    options.afterPass?.(request.stages, result);
    return result;
  };
  if (plan.gpu) await warmKernels(sandbox, options.backends ?? DEFAULT_BACKENDS);
  const first = await run({ asset: delivery.main, stages: plan.stages, args: [...plan.args, ...plan.deviceArgs], device: plan.gpu ? "gpu" : "cpu", sandbox, budgets: plan.budgets, addressSpaceUntilGpu: plan.gpu, signal });
  return { version, asset: delivery.main, sandbox, plan, mode, first, run };
}

async function closeupImages(started: Started, attempt: RenderAttempt | null, outDir: string): Promise<{ name: string; path: string }[]> {
  const { plan, sandbox, mode } = started;
  if (plan.closeupRefusal !== null) throw plan.closeupRefusal;
  if (attempt === null) throw new StageFailure({ stage: "closeups", code: "not_rendered", message: "the views did not render" });
  let result = attempt.result;
  let gpu = attempt.gpu;
  const crashed = result.interrupted?.stage === "closeups" && result.interrupted.failure.code === "crashed";
  if (crashed && gpu && mode === "auto") {
    result = await started.run({ asset: started.asset, stages: ["closeups"], args: [...plan.args, ...deviceArgs(null, [])], device: "cpu", sandbox, budgets: plan.budgets });
    gpu = false;
  }
  const outcome = closeupsAttempt(result, sandbox, gpu);
  if (!outcome.ok) throw new StageFailure({ stage: "closeups", code: "gpu_unavailable", message: outcome.message });
  return copyCloseups(sandbox, outcome.value.output, join(outDir, CLOSEUPS_FOLDER));
}

async function blenderStages(draft: Draft, spec: AssetSpec, delivery: Delivery, references: LoadedReference[] | null, started: Started, validation: Validation | null, outDir: string, options: JudgeOptions): Promise<RenderAttempt | null> {
  const { sandbox, plan, first, mode } = started;
  draft.blender = started.version;
  const measurements = measuredFrom(first, sandbox, spec, delivery, (measured) => {
    draft.sandbox = first.isolation;
    draft.timings.measure = measured;
  });
  draft.measurements = measurements;
  draft.rules = evaluateRules(spec, measurements, validation);
  if (spec.reference !== undefined && references !== null) {
    draft.reference = null;
    const output = silhouettesFrom(first, sandbox);
    const referenceSeconds = stageSeconds(first, "reference");
    if (referenceSeconds !== null) draft.timings.reference = referenceSeconds;
    referenceStage(draft, spec.reference, references, output, sandbox, outDir);
  }
  const views = (spec.views ?? DEFAULT_VIEWS).length;
  const budget = renderBudget(measurements.triangles, views, options);
  const skipped = options.preview === true ? "preview" : overBudget(budget);
  const continueWith = async (stages: PassStage[]): Promise<RenderAttempt> => {
    const all: PassStage[] = stages.includes("views") && plan.closeups ? [...stages, "closeups"] : stages;
    const budgets = { ...plan.budgets, render: stages.includes("views") ? plan.budgets.render : sandbox.limits.timeoutMs };
    const result = await started.run({ asset: delivery.main, stages: all, args: [...plan.args, ...deviceArgs(null, [])], device: "cpu", sandbox, budgets });
    return { result, sandbox, gpu: false, fallback: true };
  };
  return interpretRenders(draft, { skipped, budget }, { result: first, sandbox, gpu: plan.gpu, fallback: false }, mode ?? "cpu", continueWith, outDir);
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
    asset: { path: assetPath, sha256: null, bytes: null, files: [], setSha256: null, setBytes: null },
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
    const references: LoadedReference[] | null = spec.reference === undefined ? null : loadReferences(spec.reference, specPath);
    checkAsset(assetPath, options.maxFileBytes ?? DEFAULTS.maxFileBytes);
    const format = extname(assetPath).slice(1).toLowerCase();
    const delivery = deliver(draft, assetPath, format, workDir, options.maxFileBytes ?? DEFAULTS.maxFileBytes);
    options.afterCopy?.(delivery);
    const abort = new AbortController();
    const blender = startBlender(spec, delivery, references, workDir, limits, maxTriangles, options, abort.signal);
    blender.catch(() => undefined);
    let validation: Validation | null;
    try {
      validation = await validationStage(draft, spec, delivery.main, outDir, options, limits.timeoutMs);
    } catch (error) {
      abort.abort();
      await blender.catch(() => undefined);
      throw error;
    }
    const bundle = await blender;
    let attempt: RenderAttempt | null = null;
    try {
      attempt = await blenderStages(draft, spec, delivery, references, bundle, validation, outDir, options);
    } finally {
      collectOutputs(workDir, outDir, draft);
    }
    draft.rules.push(...renderRules(spec, draft.renders));
    if (spec.visual !== undefined) {
      const rendered = attempt;
      draft.visual = await visualStage({ spec, renders: draft.renders, outDir, closeups: () => closeupImages(bundle, rendered, outDir), options: options.visual ?? {} });
      const closeupSeconds = rendered === null ? null : stageSeconds(rendered.result, "closeups");
      if (closeupSeconds !== null) draft.timings.closeups = closeupSeconds;
      draft.rules.push(...visualRules(draft.visual));
    }
    if (wantsPackage(spec)) await packageStage(draft, spec, delivery, bundle.sandbox, outDir, maxTriangles, options);
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    draft.failure = error.failure;
    collectOutputs(workDir, outDir, draft);
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
  if (draft.failure) draft.rules.unshift({ rule: draft.failure.stage, measured: draft.failure.message, limit: "to complete", pass: false });
  draft.passed = draft.failure === null && draft.rules.length > 0 && draft.rules.every((rule) => rule.pass);
  draft.timings.total = seconds(performance.now() - started);
  const report: Report = { ...draft, summary: summarize(draft) };
  writeJson(join(outDir, "report.json"), report);
  writeFileSync(join(outDir, "summary.txt"), `${report.summary}\n`);
  return report;
}
