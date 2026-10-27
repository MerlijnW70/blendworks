import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { blenderPath } from "../blender.js";
import { copyDelivery, DeliveryError } from "../judge/delivery.js";
import { DeviceError, deviceModeFromEnvironment, type DeviceMode } from "../judge/device.js";
import { detectTools, type Tools } from "../judge/sandbox.js";
import { parseSpec, SpecError, type AssetSpec } from "../judge/spec.js";
import { checkAsset, checkBlender, DEFAULTS, deviceMode, StageFailure, workOut, type Sandbox } from "../judge/stages.js";
import { packageStem } from "./judge-stage.js";
import { runPackage, type PackageContext } from "./pipeline.js";
import { packageLines, type PackageConfig, type PackageReport } from "./report.js";
import { packageResults } from "./rules.js";

export const PACKAGE_USAGE = `usage: blendworks package <asset> --out <dir> [--lods n] [--ratios 0.5,0.25] [--max-screen-error px --distances m,m]
  [--min-iou x] [--min-similarity x] [--files single|separate] [--ktx2] [--no-meshopt] [--max-bytes n] [--views front,top]
  [--timeout seconds] [--memory-mb n] [--max-triangles n] [--max-file-mb n]

Builds a game-ready package from a .glb, .gltf, .fbx, .obj or .blend asset in a sandboxed headless Blender 5.2:
LOD1..LODn (named <name>_LOD<n>) by Blender decimation that keeps borders, material boundaries and UV seams where
the target allows it, with weighted normals; the geometric error of every LOD (Hausdorff distance in metres and as a
share of the bounds); renders of each LOD against LOD0 at its switch-in distance with silhouette IoU and SSIM; then an
uncompressed package and a gltfpack-compressed package (meshopt, quantised), both checked with the Khronos validator and
against each other. Writes uncompressed/, compressed/, lods/ and package-report.json to the out dir.
Give --lods with --ratios (one per LOD, falling) or with --max-screen-error and --distances (one per LOD, rising).
Without --lods only the compressed package is made. --ktx2 asks for KTX2 textures: ETC1S for colour maps, UASTC for
normal and data maps, with full mip chains. The native gltfpack writes them (npm run tools:gltfpack installs it, or set
BLENDWORKS_GLTFPACK); the npm build cannot, so the report says so and the textures stay unchanged.
Exits 0 only when every requested check passes.`;

export class PackageUsageError extends Error {}

const MEGABYTE = 1024 * 1024;

function positive(text: string | undefined, name: string, fallback: number, unit: number): number {
  if (text === undefined) return fallback;
  if (!/^\d+$/.test(text) || Number(text) <= 0) throw new PackageUsageError(`--${name} must be a positive whole number`);
  return Number(text) * unit;
}

function numbers(text: string | undefined, name: string): number[] | undefined {
  if (text === undefined) return undefined;
  const values = text.split(",").map((part) => Number(part.trim()));
  if (values.some((value) => !Number.isFinite(value))) throw new PackageUsageError(`--${name} must be a comma-separated list of numbers`);
  return values;
}

function single(text: string | undefined, name: string): number | undefined {
  if (text === undefined) return undefined;
  const value = Number(text);
  if (!Number.isFinite(value)) throw new PackageUsageError(`--${name} must be a number`);
  return value;
}

function deviceFromEnvironment(): DeviceMode {
  try {
    return deviceModeFromEnvironment();
  } catch (error) {
    if (error instanceof DeviceError) throw new PackageUsageError(error.message);
    throw error;
  }
}

export type PackageCommand = {
  command: "package";
  assetPath: string;
  outDir: string;
  config: PackageConfig;
  spec: AssetSpec;
  device: DeviceMode;
  timeoutMs: number;
  memoryBytes: number;
  maxTriangles: number;
  maxFileBytes: number;
};

export function parsePackage(argv: string[]): PackageCommand | { help: string } {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    strict: true,
    options: {
      out: { type: "string" },
      lods: { type: "string" },
      ratios: { type: "string" },
      "max-screen-error": { type: "string" },
      distances: { type: "string" },
      "min-iou": { type: "string" },
      "min-similarity": { type: "string" },
      files: { type: "string" },
      ktx2: { type: "boolean" },
      "no-meshopt": { type: "boolean" },
      "max-bytes": { type: "string" },
      views: { type: "string" },
      timeout: { type: "string" },
      "memory-mb": { type: "string" },
      "max-triangles": { type: "string" },
      "max-file-mb": { type: "string" },
      help: { type: "boolean", short: "h" },
    },
  });
  if (values.help) return { help: PACKAGE_USAGE };
  const [assetPath, ...extra] = positionals;
  if (assetPath === undefined || values.out === undefined || extra.length > 0) throw new PackageUsageError(PACKAGE_USAGE);
  const lods = values.lods === undefined ? undefined : positive(values.lods, "lods", 1, 1);
  const lodsRule =
    lods === undefined
      ? undefined
      : {
          count: lods,
          ...(values.ratios === undefined ? {} : { ratios: numbers(values.ratios, "ratios") }),
          ...(values["max-screen-error"] === undefined ? {} : { maxScreenError: single(values["max-screen-error"], "max-screen-error") }),
          ...(values.distances === undefined ? {} : { distances: numbers(values.distances, "distances") }),
          ...(values["min-iou"] === undefined ? {} : { minSilhouetteIoU: single(values["min-iou"], "min-iou") }),
          ...(values["min-similarity"] === undefined ? {} : { minSimilarity: single(values["min-similarity"], "min-similarity") }),
          ...(values.files === undefined ? {} : { files: values.files }),
        };
  const packageRule = {
    ...(values.ktx2 === true ? { ktx2: true } : {}),
    ...(values["no-meshopt"] === true ? { meshopt: false } : {}),
    ...(values["max-bytes"] === undefined ? {} : { compressedMaxBytes: positive(values["max-bytes"], "max-bytes", 1, 1) }),
  };
  let spec: AssetSpec;
  try {
    spec = parseSpec({ format: extname(assetPath).slice(1).toLowerCase() || "glb", ...(lodsRule === undefined ? {} : { lods: lodsRule }), package: packageRule });
  } catch (error) {
    if (error instanceof SpecError) throw new PackageUsageError(error.message);
    throw error;
  }
  const views = values.views === undefined ? undefined : values.views.split(",").filter((view) => view.length > 0);
  return {
    command: "package",
    assetPath,
    outDir: values.out,
    config: { ...(spec.lods === undefined ? {} : { lods: spec.lods }), package: spec.package ?? {}, ...(views === undefined ? {} : { views }) },
    spec,
    device: deviceFromEnvironment(),
    timeoutMs: positive(values.timeout, "timeout", 1_800_000, 1000),
    memoryBytes: positive(values["memory-mb"], "memory-mb", DEFAULTS.memoryBytes, MEGABYTE),
    maxTriangles: positive(values["max-triangles"], "max-triangles", DEFAULTS.maxTriangles, 1),
    maxFileBytes: positive(values["max-file-mb"], "max-file-mb", DEFAULTS.maxFileBytes, MEGABYTE),
  };
}

export type PackageRun = { report: PackageReport; passed: boolean; summary: string };

export type PackageHooks = { tools?: Tools; compressor?: PackageContext["compressor"] };

export async function packageAsset(command: Omit<PackageCommand, "command">, hooks: PackageHooks = {}): Promise<PackageRun> {
  const assetPath = resolve(command.assetPath);
  const outDir = resolve(command.outDir);
  checkAsset(assetPath, command.maxFileBytes);
  const blender = blenderPath();
  await checkBlender(blender);
  deviceMode(command.device);
  mkdirSync(outDir, { recursive: true });
  const workDir = mkdtempSync(join(tmpdir(), "blendworks-package-"));
  try {
    let delivered: string;
    let folder: string;
    try {
      ({ main: delivered, folder } = copyDelivery(assetPath, extname(assetPath).slice(1).toLowerCase(), workDir, command.maxFileBytes));
    } catch (error) {
      if (error instanceof DeliveryError) throw new StageFailure({ stage: "asset", code: error.code, message: error.message });
      throw error;
    }
    const sandbox: Sandbox = { blender, limits: { timeoutMs: command.timeoutMs, memoryBytes: command.memoryBytes }, tools: hooks.tools ?? detectTools(blender), workDir, delivery: folder };
    mkdirSync(workOut(sandbox), { recursive: true });
    const report = await runPackage(command.config, {
      assetPath: delivered,
      outDir,
      sandbox,
      stem: packageStem(undefined, assetPath),
      maxTriangles: command.maxTriangles,
      device: command.device,
      ...(hooks.compressor === undefined ? {} : { compressor: hooks.compressor }),
    });
    const rules = packageResults(command.spec, report);
    const passed = rules.every((rule) => rule.pass);
    const lines = [`${passed ? "PASS" : "FAIL"}  package  (${assetPath})`];
    for (const rule of rules) lines.push(`  ${rule.pass ? "pass" : "FAIL"}  ${rule.rule}  measured ${JSON.stringify(rule.measured)}; required ${JSON.stringify(rule.limit)}`);
    lines.push(...packageLines(report));
    return { report, passed, summary: lines.join("\n") };
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
