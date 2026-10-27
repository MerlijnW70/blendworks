import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { blenderPath } from "../blender.js";
import { copyDelivery, DeliveryError } from "./delivery.js";
import { REFERENCE_LIMITS, renderedMask, renderSilhouettes } from "./reference.js";
import { detectTools, type Tools } from "./sandbox.js";
import { maskImage } from "./silhouette.js";
import { VIEWS } from "./spec-shapes.js";
import { checkAsset, checkBlender, DEFAULTS, StageFailure, workOut, type Sandbox } from "./stages.js";
import { encodePng } from "./visual/png.js";

export const SILHOUETTE_DEFAULTS = { size: 512, views: ["front"] as (typeof VIEWS)[number][], timeoutMs: 300_000 };

export type SilhouettesOptions = {
  assetPath: string;
  outDir: string;
  views?: (typeof VIEWS)[number][];
  size?: number;
  upAxis?: "z" | "y";
  blender?: string;
  timeoutMs?: number;
  memoryBytes?: number;
  maxTriangles?: number;
  maxFileBytes?: number;
  tools?: Tools;
};

export type SilhouettesResult = {
  asset: string;
  masks: { view: string; path: string; sha256: string; pixels: number }[];
  reference: { views: Record<string, { sha256: string; mask: string }>; bounds: { min: number[]; max: number[] } };
};

export function fromBlender(point: readonly number[], axis: "z" | "y"): number[] {
  const [x = 0, y = 0, z = 0] = point;
  return axis === "y" ? [x, z, -y] : [x, y, z];
}

function specBounds(min: readonly number[], max: readonly number[], axis: "z" | "y"): { min: number[]; max: number[] } {
  const corners = [fromBlender(min, axis), fromBlender(max, axis)];
  const round = (value: number) => Math.round(value * 1e6) / 1e6 + 0;
  return {
    min: [0, 1, 2].map((index) => round(Math.min(corners[0]![index]!, corners[1]![index]!))),
    max: [0, 1, 2].map((index) => round(Math.max(corners[0]![index]!, corners[1]![index]!))),
  };
}

export async function silhouettes(options: SilhouettesOptions): Promise<SilhouettesResult> {
  const assetPath = resolve(options.assetPath);
  const outDir = resolve(options.outDir);
  const size = options.size ?? SILHOUETTE_DEFAULTS.size;
  const views = options.views ?? SILHOUETTE_DEFAULTS.views;
  if (!Number.isInteger(size) || size < REFERENCE_LIMITS.minSide || size > REFERENCE_LIMITS.maxSide) {
    throw new StageFailure({ stage: "reference", code: "usage", message: `--size must be ${REFERENCE_LIMITS.minSide} to ${REFERENCE_LIMITS.maxSide} pixels` });
  }
  const maxFileBytes = options.maxFileBytes ?? DEFAULTS.maxFileBytes;
  checkAsset(assetPath, maxFileBytes);
  const blender = options.blender ?? blenderPath();
  await checkBlender(blender);
  mkdirSync(outDir, { recursive: true });
  const workDir = mkdtempSync(join(tmpdir(), "blendworks-silhouettes-"));
  try {
    let delivered: string;
    let folder: string;
    try {
      ({ main: delivered, folder } = copyDelivery(assetPath, extname(assetPath).slice(1).toLowerCase(), workDir, maxFileBytes));
    } catch (error) {
      if (error instanceof DeliveryError) throw new StageFailure({ stage: "asset", code: error.code, message: error.message });
      throw error;
    }
    const limits = { timeoutMs: options.timeoutMs ?? SILHOUETTE_DEFAULTS.timeoutMs, memoryBytes: options.memoryBytes ?? DEFAULTS.memoryBytes };
    const sandbox: Sandbox = { blender, limits, tools: options.tools ?? detectTools(blender), workDir, delivery: folder };
    mkdirSync(workOut(sandbox), { recursive: true });
    const output = await renderSilhouettes(delivered, views.map((view) => ({ view, size })), sandbox, options.maxTriangles ?? DEFAULTS.maxTriangles);
    const masks = views.map((view) => {
      const mask = renderedMask(sandbox, view);
      const data = encodePng(maskImage(mask));
      const path = join(outDir, `${view}.png`);
      writeFileSync(path, data);
      return { view, path, sha256: createHash("sha256").update(data).digest("hex"), pixels: mask.inside.reduce((sum, value) => sum + value, 0) };
    });
    const reference = {
      views: Object.fromEntries(masks.map((mask) => [mask.view, { sha256: mask.sha256, mask: basename(mask.path) }])),
      bounds: specBounds(output.frame.min, output.frame.max, options.upAxis ?? "z"),
    };
    const result = { asset: assetPath, masks, reference };
    writeFileSync(join(outDir, "silhouettes.json"), `${JSON.stringify(result, null, 2)}\n`);
    return result;
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

export function silhouettesSummary(result: SilhouettesResult): string {
  const lines = [`silhouettes of ${result.asset}:`];
  for (const mask of result.masks) lines.push(`  ${mask.view}: ${mask.path}, ${mask.pixels} pixels inside, sha256 ${mask.sha256}`);
  lines.push("reference for the spec, with the masks beside it:", JSON.stringify({ reference: result.reference }, null, 2));
  return lines.join("\n");
}
