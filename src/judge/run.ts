import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { blenderPath } from "../blender.js";
import { copyDelivery, DeliveryError, type Delivery } from "./delivery.js";
import type { DeviceMode } from "./device.js";
import { renderRules } from "./integrity-rules.js";
import { measureOutputSchema, measurementsSchema, type Measurements } from "./measurements.js";
import { motionExtras, withBoneScheme } from "./motion-rules.js";
import { weightTolerance } from "./motion-spec.js";
import { loadReferences, referenceStage, REFERENCE_FOLDER, type LoadedReference } from "./reference.js";
import { upAxis } from "./shape-rules.js";
import { wantsObjectList } from "./object-rules.js";
import { hashRenders, renderStage, uvGridPath } from "./render-stage.js";
import { summarize, type Report, type Timings } from "./report.js";
import { evaluateRules } from "./rules.js";
import { detectTools, type Limits, type Tools } from "./sandbox.js";
import { readSpec, SpecError, type AssetSpec } from "./spec.js";
import { checkAsset, checkBlender, DEFAULTS, deviceMode, runScript, seconds, sha256, StageFailure, workOut, type Sandbox } from "./stages.js";
import { floatingTolerance, validatorRules } from "./texture-rules.js";
import { packageStage } from "../package/judge-stage.js";
import { wantsPackage } from "../package/rules.js";
import { validateGltf, ValidationError, VALIDATOR_DEFAULTS, type Validation } from "./validator.js";
import { visualStage } from "./visual/judge-stage.js";
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
  visual?: VisualOptions;
};

const OUTPUTS = ["report.json", "summary.txt", "measurements.json", "validation.json", "render.json", "contact-sheet.png", "views", "visual.json", "visual", "closeups", "package", REFERENCE_FOLDER];
const STAGE_OUTPUTS = ["measurements.json", "render.json", "contact-sheet.png"];

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

function reported(spec: AssetSpec, measurements: Measurements): Measurements {
  if (spec.textures !== undefined) return measurements;
  const { textures: _, ...rest } = measurements;
  return rest;
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

async function measureStage(draft: Draft, spec: AssetSpec, delivery: Delivery, sandbox: Sandbox, maxTriangles: number): Promise<Measurements> {
  const measurementsPath = join(workOut(sandbox), "measurements.json");
  const measureArgs = [delivery.main, measurementsPath, "--max-triangles", String(maxTriangles), "--uv-grid", uvGridPath(sandbox)];
  const tolerance = floatingTolerance(spec);
  if (tolerance !== undefined) measureArgs.push("--floating-tolerance", String(tolerance));
  if (wantsObjectList(spec)) measureArgs.push("--objects", "yes");
  const extras = motionExtras(spec);
  if (extras.length > 0) measureArgs.push("--extras", extras.join(","), "--weight-tolerance", String(weightTolerance(spec.skin)));
  const measured = await runScript("measure", "measure.py", measureArgs, measurementsPath, sandbox);
  draft.sandbox = measured.isolation;
  draft.timings.measure = measured.seconds;
  const parsed = measureOutputSchema.safeParse(measured.output);
  if (!parsed.success) throw new StageFailure({ stage: "measure", code: "malformed", message: "the measuring script wrote malformed output" });
  if (!parsed.data.ok) throw new StageFailure({ stage: "measure", ...parsed.data.error });
  const { format, ...rest } = parsed.data.measurements;
  return withBoneScheme(spec, reported(spec, measurementsSchema.parse({ format, fileBytes: delivery.bytes, ...rest, references: delivery.references })));
}

function collectOutputs(workDir: string, outDir: string, draft: Draft): void {
  const out = join(workDir, "out");
  for (const name of STAGE_OUTPUTS) if (existsSync(join(out, name))) copyFileSync(join(out, name), join(outDir, name));
  const views = draft.renders?.views ?? [];
  if (views.length > 0) mkdirSync(join(outDir, "views"), { recursive: true });
  for (const view of views) cpSync(join(out, "views", basename(view.path)), view.path);
  if (draft.renders?.contactSheet && !existsSync(draft.renders.contactSheet)) draft.renders.contactSheet = null;
  hashRenders(draft.renders);
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
    const validation = await validationStage(draft, spec, delivery.main, outDir, options, limits.timeoutMs);
    const blender = options.blender ?? blenderPath();
    draft.blender = await checkBlender(blender);
    if (options.preview !== true) deviceMode(options.device);
    const sandbox: Sandbox = { blender, limits, tools: options.tools ?? detectTools(blender), workDir, delivery: delivery.folder };
    mkdirSync(workOut(sandbox), { recursive: true });
    const measurements = await measureStage(draft, spec, delivery, sandbox, maxTriangles);
    draft.measurements = measurements;
    draft.rules = evaluateRules(spec, measurements, validation);
    if (spec.reference !== undefined && references !== null) {
      draft.reference = null;
      await referenceStage(draft, spec.reference, references, delivery.main, sandbox, outDir, maxTriangles, upAxis(spec));
    }
    try {
      await renderStage(draft, spec, delivery.main, outDir, sandbox, maxTriangles, options);
    } finally {
      collectOutputs(workDir, outDir, draft);
    }
    draft.rules.push(...renderRules(spec, draft.renders));
    if (spec.visual !== undefined) {
      const maxFileBytes = options.maxFileBytes ?? DEFAULTS.maxFileBytes;
      const extra = { ...(options.device ? { device: options.device } : {}), ...(options.backends ? { backends: options.backends } : {}) };
      draft.visual = await visualStage({ spec, renders: draft.renders, assetPath: delivery.main, outDir, sandbox, maxTriangles, maxFileBytes, ...extra, options: options.visual ?? {} });
      draft.rules.push(...visualRules(draft.visual));
    }
    if (wantsPackage(spec)) await packageStage(draft, spec, delivery, sandbox, outDir, maxTriangles, options);
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
