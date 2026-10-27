import type { ValidationInfo } from "../judge/validator.js";
import type { Analysis } from "./analysis.js";
import type { GlbParts } from "./glb.js";
import type { Ktx2Info } from "./ktx2.js";
import { readImages } from "./textures.js";

export const IMAGE_FORMATS = ["rgba8", "uastc", "etc1s", "other"] as const;
export type ImageFormat = (typeof IMAGE_FORMATS)[number];

export type ImageMemory = { image: number; width: number; height: number; format: ImageFormat; levels: number; alpha: boolean; bytes: number };

export type GpuMemory = { textureBytes: number; meshBytes: number; totalBytes: number; images: ImageMemory[] };

export type BlockOptions = { levels?: number; alpha?: boolean };

const BLOCK_PIXELS = 4;
const UASTC_BLOCK_BYTES = 16;
const ETC1S_BLOCK_BYTES = 8;
const ETC1S_ALPHA_BLOCK_BYTES = 16;

export function mipChain(width: number, height: number): [number, number][] {
  const levels: [number, number][] = [[width, height]];
  let w = width;
  let h = height;
  while (w > 1 || h > 1) {
    w = Math.max(1, Math.floor(w / 2));
    h = Math.max(1, Math.floor(h / 2));
    levels.push([w, h]);
  }
  return levels;
}

export function blockBytes(format: Exclude<ImageFormat, "rgba8" | "other">, alpha: boolean): number {
  if (format === "uastc") return UASTC_BLOCK_BYTES;
  return alpha ? ETC1S_ALPHA_BLOCK_BYTES : ETC1S_BLOCK_BYTES;
}

export function imageBytes(width: number, height: number, format: Exclude<ImageFormat, "other">, options: BlockOptions = {}): number {
  const chain = mipChain(width, height).slice(0, options.levels ?? Infinity);
  let total = 0;
  for (const [w, h] of chain) {
    total += format === "rgba8" ? 4 * w * h : Math.ceil(w / BLOCK_PIXELS) * Math.ceil(h / BLOCK_PIXELS) * blockBytes(format, options.alpha === true);
  }
  return total;
}

function compressedMemory(index: number, header: Ktx2Info): ImageMemory {
  const { width, height, levelCount, alpha, codec } = header;
  if (codec === "other") {
    const bytes = header.levels.reduce((sum, level) => sum + level.bytes, 0);
    return { image: index, width, height, format: "other", levels: levelCount, alpha, bytes };
  }
  return { image: index, width, height, format: codec, levels: levelCount, alpha, bytes: imageBytes(width, height, codec, { levels: levelCount, alpha }) };
}

export function gpuMemory(parts: GlbParts, analysis: Analysis, info: ValidationInfo): GpuMemory {
  const images: ImageMemory[] = [];
  for (const image of readImages(parts, analysis, info)) {
    if (image.ktx2 !== null) {
      images.push(compressedMemory(image.index, image.ktx2));
    } else if (image.error === null && image.width !== null && image.height !== null) {
      images.push({
        image: image.index,
        width: image.width,
        height: image.height,
        format: "rgba8",
        levels: mipChain(image.width, image.height).length,
        alpha: true,
        bytes: imageBytes(image.width, image.height, "rgba8"),
      });
    }
  }
  const textureBytes = images.reduce((sum, entry) => sum + entry.bytes, 0);
  return { textureBytes, meshBytes: analysis.accessorBytes, totalBytes: textureBytes + analysis.accessorBytes, images };
}
