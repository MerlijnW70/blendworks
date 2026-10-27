import { createHash } from "node:crypto";
import { closeSync, fstatSync, lstatSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { z } from "zod";
import type { Measurements } from "./measurements.js";
import type { Report } from "./report.js";
import type { ReferenceRule } from "./reference-spec.js";
import { toBlender, type RuleResult } from "./shape-rules.js";
import { compareMasks, maskChannel, maskFromPixels, maskImage, overlayImage, type Mask, type MaskChannel } from "./silhouette.js";
import { VIEWS } from "./spec-shapes.js";
import { passOutput, runPass, type PassResult } from "./onepass.js";
import { readShared } from "./shared-access.js";
import { StageFailure, workOut, type Sandbox } from "./stages.js";
import { decodePng, encodePng, PNG_SIGNATURE, PngError } from "./visual/png.js";

export const REFERENCE_LIMITS = { maxBytes: 8 * 1024 * 1024, minSide: 16, maxSide: 2048 };
export const REFERENCE_FOLDER = "reference";

type Draft = Omit<Report, "summary">;

export type LoadedReference = { view: string; mask: string; sha256: string; bytes: number; size: number; channel: MaskChannel; inside: Mask };

export type ReferenceView = Omit<LoadedReference, "inside"> & {
  assetPixels: number;
  referencePixels: number;
  intersection: number;
  union: number;
  iou: number;
  boundaryPixels: number | null;
  boundaryDistance: number | null;
  edges: { asset: number; reference: number };
  silhouette: string;
  silhouetteSha256: string;
  overlay: string;
  overlaySha256: string;
};

export type ReferenceRecord = { frame: { source: "spec" | "asset"; min: number[]; max: number[] }; views: ReferenceView[] };

const silhouetteOutput = z.union([
  z.object({
    ok: z.literal(true),
    views: z.array(z.object({ view: z.enum(VIEWS), path: z.string(), size: z.number().int().positive() })).max(VIEWS.length),
    frame: z.object({ min: z.tuple([z.number(), z.number(), z.number()]), max: z.tuple([z.number(), z.number(), z.number()]) }),
  }),
  z.object({ ok: z.literal(false), error: z.object({ code: z.string().max(64), message: z.string().max(2000) }) }),
]);

export type SilhouetteOutput = Extract<z.infer<typeof silhouetteOutput>, { ok: true }>;

function digest(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

function refuse(view: string, code: string, message: string): never {
  throw new StageFailure({ stage: "reference", code, message: `the ${view} reference ${message}` });
}

function pngSide(data: Buffer, view: string): number {
  if (data.length < 24 || !data.subarray(0, 8).equals(PNG_SIGNATURE) || data.toString("latin1", 12, 16) !== "IHDR") refuse(view, "reference_format", "is not a PNG file");
  const width = data.readUInt32BE(16);
  const height = data.readUInt32BE(20);
  if (width !== height) refuse(view, "reference_dimensions", `is ${width} x ${height} pixels; it must be square`);
  if (width < REFERENCE_LIMITS.minSide || width > REFERENCE_LIMITS.maxSide) {
    refuse(view, "reference_dimensions", `is ${width} pixels on a side; it must be ${REFERENCE_LIMITS.minSide} to ${REFERENCE_LIMITS.maxSide}`);
  }
  return width;
}

function inside(path: string, folder: string): boolean {
  const offset = relative(folder, path);
  return offset !== "" && !offset.startsWith("..") && !isAbsolute(offset);
}

function readMask(folder: string, view: string, mask: string): Buffer {
  const target = resolve(folder, mask);
  let real: string;
  try {
    real = realpathSync(target);
  } catch {
    refuse(view, "reference_missing", `${mask} is not beside the spec`);
  }
  if (!inside(real, folder)) refuse(view, "reference_outside", `${mask} leads outside the spec's folder`);
  if (!lstatSync(real).isFile()) refuse(view, "reference_not_a_file", `${mask} is not a file`);
  const handle = openSync(real, "r");
  try {
    const stats = fstatSync(handle);
    if (!stats.isFile()) refuse(view, "reference_not_a_file", `${mask} is not a file`);
    if (stats.size > REFERENCE_LIMITS.maxBytes) refuse(view, "reference_too_large", `${mask} is ${stats.size} bytes, over the limit of ${REFERENCE_LIMITS.maxBytes}`);
    const buffer = Buffer.alloc(REFERENCE_LIMITS.maxBytes + 1);
    let filled = 0;
    while (filled < buffer.length) {
      const read = readSync(handle, buffer, filled, buffer.length - filled, filled);
      if (read === 0) break;
      filled += read;
    }
    if (filled > REFERENCE_LIMITS.maxBytes) refuse(view, "reference_too_large", `${mask} is over the limit of ${REFERENCE_LIMITS.maxBytes} bytes`);
    return buffer.subarray(0, filled);
  } finally {
    closeSync(handle);
  }
}

export function loadReferences(rule: ReferenceRule, specPath: string): LoadedReference[] {
  const folder = realpathSync(dirname(resolve(specPath)));
  const loaded: LoadedReference[] = [];
  for (const view of VIEWS) {
    const entry = rule.views[view];
    if (entry === undefined) continue;
    const data = readMask(folder, view, entry.mask);
    const sha256 = digest(data);
    if (sha256 !== entry.sha256) refuse(view, "reference_sha256", `${entry.mask} has sha256 ${sha256}, not the pinned ${entry.sha256}`);
    const size = pngSide(data, view);
    let pixels;
    try {
      pixels = decodePng(data);
    } catch (error) {
      if (error instanceof PngError) refuse(view, "reference_format", `${entry.mask} is a malformed PNG: ${error.message}`);
      throw error;
    }
    const channel = maskChannel(pixels);
    loaded.push({ view, mask: entry.mask, sha256, bytes: data.length, size, channel, inside: maskFromPixels(pixels, channel) });
  }
  return loaded;
}

export function referenceFrame(rule: ReferenceRule, measurements: Measurements | null, axis: "z" | "y"): { source: "spec" | "asset"; min: number[]; max: number[]; origin: number[] } {
  if (rule.bounds === undefined) {
    if (measurements === null) throw new Error("the reference frame needs the asset's measurements or the spec's bounds");
    return { source: "asset", min: measurements.bounds.min, max: measurements.bounds.max, origin: measurements.origin.point };
  }
  const corners = [toBlender(rule.bounds.min, axis), toBlender(rule.bounds.max, axis)];
  const min = [0, 1, 2].map((index) => Math.min(corners[0]![index]!, corners[1]![index]!));
  const max = [0, 1, 2].map((index) => Math.max(corners[0]![index]!, corners[1]![index]!));
  return { source: "spec", min, max, origin: min.map((low, index) => (low + max[index]!) / 2) };
}

export function silhouetteArgs(views: { view: string; size: number }[], frame: { min: number[]; max: number[]; origin: number[] } | "asset" | "measured"): string[] {
  const args = ["--reference-views", views.map((entry) => `${entry.view}:${entry.size}`).join(",")];
  if (frame === "asset" || frame === "measured") args.push("--reference-frame", frame);
  else args.push("--reference-frame", [...frame.min, ...frame.max].join(","), "--reference-origin", frame.origin.join(","));
  return args;
}

export function silhouettesFrom(result: PassResult, sandbox: Sandbox): SilhouetteOutput {
  if (result.interrupted !== null && result.interrupted.stage === "reference") throw new StageFailure(result.interrupted.failure);
  const parsed = silhouetteOutput.safeParse(passOutput(sandbox, "reference"));
  if (!parsed.success) throw new StageFailure({ stage: "reference", code: "malformed", message: "the silhouette script wrote malformed output" });
  if (!parsed.data.ok) throw new StageFailure({ stage: "reference", ...parsed.data.error });
  return parsed.data;
}

export async function renderSilhouettes(asset: string, views: { view: string; size: number }[], sandbox: Sandbox, maxTriangles: number): Promise<SilhouetteOutput> {
  const budgets = { measure: sandbox.limits.timeoutMs, reference: sandbox.limits.timeoutMs, render: sandbox.limits.timeoutMs, closeups: sandbox.limits.timeoutMs };
  const args = [...silhouetteArgs(views, "asset"), "--max-triangles", String(maxTriangles)];
  const result = await runPass({ asset, stages: ["reference"], args, device: "cpu", sandbox, budgets });
  return silhouettesFrom(result, sandbox);
}

export function renderedMask(sandbox: Sandbox, view: string): Mask {
  return maskFromPixels(decodePng(readShared(join(workOut(sandbox), "silhouettes", `${view}.png`))), "alpha");
}

function writeImage(path: string, image: Parameters<typeof encodePng>[0]): string {
  const data = encodePng(image);
  writeFileSync(path, data);
  return digest(data);
}

export function referencePassFrame(rule: ReferenceRule, axis: "z" | "y"): { min: number[]; max: number[]; origin: number[] } | "measured" {
  if (rule.bounds === undefined) return "measured";
  const { source: _, ...frame } = referenceFrame(rule, null, axis);
  return frame;
}

export function referenceStage(draft: Draft, rule: ReferenceRule, references: LoadedReference[], output: SilhouetteOutput, sandbox: Sandbox, outDir: string): void {
  const folder = join(outDir, REFERENCE_FOLDER);
  mkdirSync(folder, { recursive: true });
  const views = references.map(({ inside: referenceMask, ...reference }): ReferenceView => {
    const assetMask = renderedMask(sandbox, reference.view);
    const silhouette = join(folder, `${reference.view}-silhouette.png`);
    const overlay = join(folder, `${reference.view}-overlay.png`);
    const compared = compareMasks(assetMask, referenceMask);
    return { ...reference, ...compared, silhouette, silhouetteSha256: writeImage(silhouette, maskImage(assetMask)), overlay, overlaySha256: writeImage(overlay, overlayImage(assetMask, referenceMask)) };
  });
  draft.reference = { frame: { source: rule.bounds === undefined ? "asset" : "spec", min: output.frame.min, max: output.frame.max }, views };
  draft.rules.push(...referenceRules(rule, draft.reference));
}

const KINDS = [
  { kind: "minIoU", value: (view: ReferenceView) => view.iou, worst: (values: number[]) => Math.min(...values), pass: (value: number, limit: number) => value >= limit },
  { kind: "maxBoundaryDistance", value: (view: ReferenceView) => view.boundaryDistance, worst: (values: number[]) => Math.max(...values), pass: (value: number, limit: number) => value <= limit },
] as const;

export function referenceRules(rule: ReferenceRule, record: ReferenceRecord): RuleResult[] {
  const results: RuleResult[] = [];
  for (const { kind, value, worst, pass } of KINDS) {
    const overall = rule[kind];
    const shared = record.views.filter((view) => rule.views[view.view as (typeof VIEWS)[number]]?.[kind] === undefined);
    if (overall !== undefined && shared.length > 0) {
      const values = shared.map(value);
      const measured = values.some((entry) => entry === null) ? null : worst(values as number[]);
      results.push({ rule: `reference.${kind}`, measured: { worst: measured, views: Object.fromEntries(shared.map((view) => [view.view, value(view)])) }, limit: overall, pass: measured !== null && pass(measured, overall) });
    }
    for (const view of record.views) {
      const own = rule.views[view.view as (typeof VIEWS)[number]]?.[kind];
      if (own === undefined) continue;
      const measured = value(view);
      results.push({ rule: `reference[${view.view}].${kind}`, measured, limit: own, pass: measured !== null && pass(measured, own) });
    }
  }
  return results;
}

export function referenceLines(record: ReferenceRecord): string[] {
  const lines = [`  reference: framed on the ${record.frame.source === "spec" ? "spec's bounds" : "asset's bounds"} [${record.frame.min.join(", ")}] to [${record.frame.max.join(", ")}]`];
  for (const view of record.views) {
    const distance = view.boundaryDistance === null ? "no boundary distance (one silhouette is empty)" : `boundary distance ${view.boundaryDistance} of the view (${view.boundaryPixels} px)`;
    lines.push(`    ${view.view}: IoU ${view.iou}, ${distance}; ${view.size} px mask ${view.mask} read by ${view.channel}; overlay ${view.overlay}`);
  }
  return lines;
}
