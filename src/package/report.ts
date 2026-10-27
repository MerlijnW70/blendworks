import type { RenderDevice } from "../judge/device.js";
import type { Validation } from "../judge/validator.js";
import type { Check, Equivalence } from "./equivalence.js";
import type { GpuMemory } from "./memory.js";
import type { Level, RenderedLevel } from "./schemas.js";
import type { GltfpackInfo } from "./tool.js";
import type { LodsRule, PackageRule } from "../judge/spec.js";

export type PackageConfig = { lods?: LodsRule; package?: PackageRule; views?: readonly string[] };

export type LodReport = Level & { render: RenderedLevel | null };

export type RenderRecord = {
  status: "rendered" | "skipped" | "failed";
  reason: string | null;
  device: RenderDevice | null;
  views: string[];
  samples: number;
  sheet: string | null;
  sheetSha256: string | null;
  budget: { samplePixels: number; maxSamplePixels: number };
};

export type Ktx2Status = "written" | "unavailable" | "not requested" | "no textures";

export type PackedFile = { path: string; bytes: number; sha256: string; validation: Validation; gpu: GpuMemory; extensionsUsed: string[] };

export type PackageFile = { level: number | null; uncompressed: PackedFile; compressed: PackedFile & { equivalence: Equivalence } };

export type Totals = { files: number; textureBytes: number; meshBytes: number; totalBytes: number };

export type PackageReport = {
  stem: string;
  layout: "single" | "separate";
  requested: { lods: LodsRule | null; package: PackageRule | null };
  levels: LodReport[];
  roundTrip: Check[] | null;
  render: RenderRecord;
  compression: { meshopt: boolean; ktx2: { requested: boolean; status: Ktx2Status; reason: string | null }; arguments: string[]; gltfpack: GltfpackInfo };
  files: PackageFile[];
  sizes: { uncompressedBytes: number; compressedBytes: number; ratio: number; gpu: { before: Totals; after: Totals } };
  seconds: number;
};

const MEBIBYTE = 1024 * 1024;

function mebibytes(bytes: number): string {
  return `${(bytes / MEBIBYTE).toFixed(2)} MiB`;
}

function levelLine(level: LodReport): string {
  if (level.level === 0) return `  LOD0  ${level.triangles} triangles`;
  const error = level.error;
  const parts = [`  LOD${level.level}  ${level.triangles} triangles (ratio ${level.ratio.toFixed(3)}${level.targetRatio ? `, target ${level.targetRatio}` : ""})`];
  if (error !== undefined) parts.push(`error ${error.hausdorff.toFixed(5)} m (${(error.hausdorffFraction * 100).toFixed(3)} % of the bounds)`);
  if (level.screenErrorPixels !== undefined && level.distance !== undefined) parts.push(`${level.screenErrorPixels.toFixed(2)} px at ${level.distance.toFixed(2)} m`);
  if (level.render !== null) parts.push(`silhouette IoU ${level.render.silhouetteIou.toFixed(4)}, SSIM ${level.render.similarity.toFixed(4)}`);
  return parts.join("; ");
}

export function gltfpackSummary(info: GltfpackInfo): string {
  const capabilities = `meshopt ${info.meshopt ? "yes" : "no"}, KTX2 ${info.ktx2 ? "yes" : `no (${info.ktx2Reason ?? "unsupported"})`}`;
  const origin = info.kind === "native" ? `${info.source}, sha256 ${info.sha256?.slice(0, 12)}` : `npm package${info.nativeSkipped === null ? "" : `, native not used: ${info.nativeSkipped}`}`;
  return `gltfpack ${info.kind} ${info.version} (${origin}; ${capabilities})`;
}

export function packageLines(report: PackageReport): string[] {
  const lines = ["  package:"];
  for (const level of report.levels) lines.push(`  ${levelLine(level)}`);
  const { render, compression, sizes } = report;
  if (render.status !== "rendered") lines.push(`    LOD renders: ${render.status}${render.reason === null ? "" : ` (${render.reason})`}`);
  if (render.sheet !== null) lines.push(`    LOD sheet: ${render.sheet}`);
  const ktx2 = compression.ktx2;
  lines.push(`    compression: ${gltfpackSummary(compression.gltfpack)}, meshopt ${compression.meshopt ? "on" : "off"}, KTX2 ${ktx2.status}${ktx2.reason === null ? "" : ` (${ktx2.reason})`}`);
  lines.push(`    size: ${mebibytes(sizes.uncompressedBytes)} uncompressed, ${mebibytes(sizes.compressedBytes)} compressed (${(sizes.ratio * 100).toFixed(1)} %)`);
  const { before, after } = sizes.gpu;
  lines.push(`    GPU memory: textures ${mebibytes(before.textureBytes)} to ${mebibytes(after.textureBytes)}, meshes ${mebibytes(before.meshBytes)} to ${mebibytes(after.meshBytes)}, total ${mebibytes(before.totalBytes)} to ${mebibytes(after.totalBytes)}`);
  for (const file of report.files) {
    const failed = file.compressed.equivalence.checks.filter((check) => !check.pass);
    lines.push(`    ${file.compressed.path}: validator ${file.compressed.validation.errors} errors, ${file.compressed.equivalence.pass ? "equivalent to the uncompressed package" : `NOT equivalent: ${failed.map((check) => `${check.name} (${check.detail})`).join("; ")}`}`);
  }
  return lines;
}
