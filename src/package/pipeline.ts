import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { StageFailure, sha256, seconds, type Sandbox } from "../judge/stages.js";
import { validateGltfDetailed, ValidationError, VALIDATOR_DEFAULTS, type Validation, type ValidationInfo } from "../judge/validator.js";
import { analyse, type Analysis } from "./analysis.js";
import {
  copyRenders,
  DEFAULT_PACKAGE_VIEWS,
  lodsStage,
  PACKAGE_RENDER_BUDGET,
  packageDir,
  renderBudgetSamplePixels,
  renderStage,
  type LodsStage,
  type RenderAttempt,
  type StageOptions,
} from "./blender-stages.js";
import { compress } from "./compress.js";
import { compareAnalyses, floatTolerance, quantisationTolerance, type Check } from "./equivalence.js";
import { parseGlb, type GlbParts } from "./glb.js";
import { readImages, type ImageDetail } from "./textures.js";
import { selectGltfpack } from "./tool.js";
import { gpuMemory } from "./memory.js";
import type { LodReport, Ktx2Status, PackageConfig, PackageFile, PackageReport, PackedFile, RenderRecord, Totals } from "./report.js";
import type { Level } from "./schemas.js";

export type PackageContext = StageOptions & {
  assetPath: string;
  outDir: string;
  sandbox: Sandbox;
  stem: string;
  deliveredTriangles?: number;
  preview?: boolean;
  compressor?: typeof compress;
};

export const PACKAGE_FOLDERS = { uncompressed: "uncompressed", compressed: "compressed", lods: "lods" } as const;
const LOD0_BOUNDS_FRACTION = 1e-4;

export type Inspected = { parts: GlbParts; analysis: Analysis; images: ImageDetail[]; validation: Validation; info: ValidationInfo; bytes: number; sha256: string };

export async function inspect(path: string, timeoutMs: number): Promise<Inspected> {
  const data = new Uint8Array(readFileSync(path));
  let result;
  try {
    result = await validateGltfDetailed(path, "glb", { maxBytes: VALIDATOR_DEFAULTS.maxBytes, heapMb: VALIDATOR_DEFAULTS.heapMb, timeoutMs });
  } catch (error) {
    if (error instanceof ValidationError) throw new StageFailure({ stage: "package", code: error.code, message: `validating ${path}: ${error.message}` });
    throw error;
  }
  const parts = parseGlb(data);
  const analysis = analyse(parts.json);
  return { parts, analysis, images: readImages(parts, analysis, result.info), validation: result.validation, info: result.info, bytes: data.byteLength, sha256: sha256(path) };
}

function packedFile(relative: string, inspected: Inspected): PackedFile {
  return {
    path: relative,
    bytes: inspected.bytes,
    sha256: inspected.sha256,
    validation: inspected.validation,
    gpu: gpuMemory(inspected.parts, inspected.analysis, inspected.info),
    extensionsUsed: inspected.analysis.extensionsUsed,
  };
}

function totals(files: PackedFile[]): Totals {
  return {
    files: files.reduce((sum, file) => sum + file.bytes, 0),
    textureBytes: files.reduce((sum, file) => sum + file.gpu.textureBytes, 0),
    meshBytes: files.reduce((sum, file) => sum + file.gpu.meshBytes, 0),
    totalBytes: files.reduce((sum, file) => sum + file.gpu.totalBytes, 0),
  };
}

function roundTrip(lods: LodsStage, rendered: RenderAttempt | null, deliveredTriangles: number | undefined): Check[] | null {
  if (rendered === null) return null;
  const checks: Check[] = [];
  const found = new Map(rendered.output.package.map((entry) => [entry.level, entry]));
  const problems: string[] = [];
  for (const level of lods.levels) {
    const entry = found.get(level.level);
    if (entry === undefined) problems.push(`LOD${level.level} is missing from the package`);
    else if (entry.triangles !== level.triangles) problems.push(`LOD${level.level} has ${entry.triangles} triangles in Blender against ${level.triangles} when written`);
  }
  checks.push({ name: "blenderImport", pass: problems.length === 0, detail: problems.length === 0 ? `Blender imports all ${lods.levels.length} levels with the written triangle counts` : problems.join("; ") });
  const zero = lods.levels.find((level) => level.level === 0);
  const imported = found.get(0);
  if (zero !== undefined && imported !== undefined) {
    const tolerance = lods.diagonal * LOD0_BOUNDS_FRACTION;
    const moved = Math.max(...imported.bounds.min.map((value, axis) => Math.abs(value - zero.bounds.min[axis]!)), ...imported.bounds.max.map((value, axis) => Math.abs(value - zero.bounds.max[axis]!)));
    const expected = deliveredTriangles ?? zero.triangles;
    const lod0Problems: string[] = [];
    if (imported.triangles !== expected) lod0Problems.push(`${imported.triangles} triangles against the delivered ${expected}`);
    if (moved > tolerance) lod0Problems.push(`the bounds moved by ${moved.toPrecision(3)} m`);
    checks.push({ name: "lod0Intact", pass: lod0Problems.length === 0, detail: lod0Problems.length === 0 ? `LOD0 keeps the delivered ${expected} triangles and bounds` : lod0Problems.join("; ") });
  }
  return checks;
}

function renderRecord(views: readonly string[], rendered: RenderAttempt | null, status: RenderRecord["status"], reason: string | null, sheet: string | null): RenderRecord {
  return {
    status,
    reason,
    device: rendered?.device ?? null,
    views: [...views],
    samples: PACKAGE_RENDER_BUDGET.samples,
    sheet,
    sheetSha256: sheet === null ? null : sha256(sheet),
    budget: { samplePixels: renderBudgetSamplePixels(0, views.length), maxSamplePixels: PACKAGE_RENDER_BUDGET.maxSamplePixels },
  };
}

type Rendering = { record: RenderRecord; attempt: RenderAttempt | null };

async function renderLevels(config: PackageConfig, lods: LodsStage, ctx: PackageContext): Promise<Rendering> {
  const views = config.views ?? DEFAULT_PACKAGE_VIEWS;
  const wanted = config.lods !== undefined && lods.levels.length > 1;
  const samplePixels = renderBudgetSamplePixels(lods.levels.length - 1, views.length);
  const skip = !wanted ? "no LODs to compare" : ctx.preview === true ? "preview" : samplePixels > PACKAGE_RENDER_BUDGET.maxSamplePixels ? `over the render budget: ${samplePixels} sample-pixels, at most ${PACKAGE_RENDER_BUDGET.maxSamplePixels}` : null;
  let attempt: RenderAttempt | null = null;
  let status: RenderRecord["status"] = "rendered";
  let reason: string | null = skip;
  try {
    attempt = await renderStage(skip === null ? views : [], ctx.sandbox, ctx);
    if (skip !== null) status = "skipped";
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    status = "failed";
    reason = error.failure.message;
    attempt = await renderStage([], ctx.sandbox, ctx).catch((measureError: unknown) => {
      if (measureError instanceof StageFailure) return null;
      throw measureError;
    });
  }
  const sheetName = attempt?.output.sheet ?? null;
  if (attempt !== null && sheetName !== null) copyRenders(ctx.sandbox, join(ctx.outDir, PACKAGE_FOLDERS.lods));
  const sheet = sheetName === null ? null : join(ctx.outDir, PACKAGE_FOLDERS.lods, sheetName);
  const record = renderRecord(views, attempt, status, reason, sheet);
  record.budget.samplePixels = samplePixels;
  return { record, attempt };
}

function levelReports(lods: LodsStage, attempt: RenderAttempt | null): LodReport[] {
  const rendered = new Map((attempt?.output.levels ?? []).map((entry) => [entry.level, entry]));
  return lods.levels.map((level: Level) => ({ ...level, render: rendered.get(level.level) ?? null }));
}

function ktx2Outcome(requested: boolean, status: Ktx2Status, reason: string | null, outputs: Inspected[]): { status: Ktx2Status; reason: string | null } {
  if (!requested || status !== "written") return { status, reason };
  const images = outputs.flatMap((output) => output.analysis.images);
  if (images.length === 0) return { status: "no textures", reason: null };
  return images.every((image) => image.mimeType === "image/ktx2")
    ? { status: "written", reason: null }
    : { status: "unavailable", reason: "gltfpack left some textures uncompressed" };
}

export async function runPackage(config: PackageConfig, ctx: PackageContext): Promise<PackageReport> {
  const started = performance.now();
  const rule = config.package ?? {};
  const meshopt = rule.meshopt ?? true;
  const ktx2Wanted = rule.ktx2 === true;
  for (const folder of Object.values(PACKAGE_FOLDERS)) rmSync(join(ctx.outDir, folder), { recursive: true, force: true });
  mkdirSync(ctx.outDir, { recursive: true });
  const lods = await lodsStage(ctx.assetPath, ctx.stem, config.lods, ctx.sandbox, ctx);
  cpSync(join(packageDir(ctx.sandbox), "lods", "uncompressed"), join(ctx.outDir, PACKAGE_FOLDERS.uncompressed), { recursive: true });
  const rendering = await renderLevels(config, lods, ctx);
  mkdirSync(join(ctx.outDir, PACKAGE_FOLDERS.compressed), { recursive: true });
  const files: PackageFile[] = [];
  const outputs: Inspected[] = [];
  let compression: Awaited<ReturnType<typeof compress>> | null = null;
  for (const entry of lods.files) {
    const name = entry.path.split("/").pop() ?? entry.path;
    const source = await inspect(join(ctx.outDir, PACKAGE_FOLDERS.uncompressed, name), ctx.sandbox.limits.timeoutMs);
    compression = await (ctx.compressor ?? compress)(new Uint8Array(readFileSync(join(ctx.outDir, PACKAGE_FOLDERS.uncompressed, name))), { meshopt, ktx2: ktx2Wanted, hasImages: source.analysis.images.length > 0, sandbox: { limits: ctx.sandbox.limits, tools: ctx.sandbox.tools } });
    const target = join(ctx.outDir, PACKAGE_FOLDERS.compressed, name);
    writeFileSync(target, compression.output);
    const packed = await inspect(target, ctx.sandbox.limits.timeoutMs);
    outputs.push(packed);
    const equivalence = compareAnalyses({
      reference: source.analysis,
      candidate: packed.analysis,
      tolerance: Math.max(quantisationTolerance(source.analysis.worldBox), floatTolerance(source.analysis.worldBox)),
      referenceInfo: source.info,
      candidateInfo: packed.info,
      textures: { referenceImages: source.images, candidateImages: packed.images, plan: { ktx2: compression.ktx2.status === "written", colourQuality: "compact" } },
    });
    files.push({
      level: entry.level,
      uncompressed: packedFile(`${PACKAGE_FOLDERS.uncompressed}/${name}`, source),
      compressed: { ...packedFile(`${PACKAGE_FOLDERS.compressed}/${name}`, packed), equivalence },
    });
  }
  const final = compression ?? { arguments: [], gltfpack: (await selectGltfpack({ limits: ctx.sandbox.limits, tools: ctx.sandbox.tools })).info, ktx2: { requested: ktx2Wanted, status: "not requested" as Ktx2Status, reason: null } };
  const ktx2 = ktx2Outcome(ktx2Wanted, final.ktx2.status, final.ktx2.reason, outputs);
  const before = totals(files.map((file) => file.uncompressed));
  const after = totals(files.map((file) => file.compressed));
  const report: PackageReport = {
    stem: lods.stem,
    layout: lods.layout,
    requested: { lods: config.lods ?? null, package: config.package ?? null },
    levels: levelReports(lods, rendering.attempt),
    roundTrip: roundTrip(lods, rendering.attempt, ctx.deliveredTriangles),
    render: rendering.record,
    compression: { meshopt, ktx2: { requested: ktx2Wanted, ...ktx2 }, arguments: final.arguments, gltfpack: final.gltfpack },
    files,
    sizes: { uncompressedBytes: before.files, compressedBytes: after.files, ratio: before.files === 0 ? 1 : after.files / before.files, gpu: { before, after } },
    seconds: seconds(performance.now() - started),
  };
  writeFileSync(join(ctx.outDir, "package-report.json"), `${JSON.stringify(report, null, 2)}\n`);
  return report;
}

export function packageOutputsExist(outDir: string): boolean {
  return existsSync(join(outDir, "package-report.json"));
}
