import type { ValidationInfo } from "../judge/validator.js";
import type { Analysis } from "./analysis.js";
import type { GlbParts } from "./glb.js";

export const IMAGE_FORMATS = ["rgba8", "uastc", "etc1s"] as const;
export type ImageFormat = (typeof IMAGE_FORMATS)[number];

export type ImageMemory = { image: number; width: number; height: number; format: ImageFormat; bytes: number };

export type GpuMemory = { textureBytes: number; meshBytes: number; totalBytes: number; images: ImageMemory[] };

const KTX2_SUPERCOMPRESSION_OFFSET = 44;
const BASIS_LZ = 1;
const BLOCK_BYTES: Record<Exclude<ImageFormat, "rgba8">, number> = { uastc: 16, etc1s: 8 };

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

export function imageBytes(width: number, height: number, format: ImageFormat): number {
  let total = 0;
  for (const [w, h] of mipChain(width, height)) {
    total += format === "rgba8" ? 4 * w * h : Math.ceil(w / 4) * Math.ceil(h / 4) * BLOCK_BYTES[format];
  }
  return total;
}

function ktx2Format(parts: GlbParts, bufferView: number | null): ImageFormat {
  const view = bufferView === null ? undefined : (parts.json.bufferViews as { byteOffset?: number }[] | undefined)?.[bufferView];
  if (view === undefined || parts.bin === null) return "uastc";
  const at = (view.byteOffset ?? 0) + KTX2_SUPERCOMPRESSION_OFFSET;
  if (at + 4 > parts.bin.byteLength) return "uastc";
  return new DataView(parts.bin.buffer, parts.bin.byteOffset).getUint32(at, true) === BASIS_LZ ? "etc1s" : "uastc";
}

export function gpuMemory(parts: GlbParts, analysis: Analysis, info: ValidationInfo): GpuMemory {
  const dimensions = new Map<number, { width: number; height: number }>();
  for (const resource of info.resources ?? []) {
    const match = /^\/images\/(\d+)$/.exec(resource.pointer);
    if (match !== null && resource.image?.width !== undefined && resource.image.height !== undefined) {
      dimensions.set(Number(match[1]), { width: resource.image.width, height: resource.image.height });
    }
  }
  const images: ImageMemory[] = [];
  analysis.images.forEach((image, index) => {
    const size = dimensions.get(index);
    if (size === undefined) return;
    const format: ImageFormat = image.mimeType === "image/ktx2" ? ktx2Format(parts, image.bufferView) : "rgba8";
    images.push({ image: index, ...size, format, bytes: imageBytes(size.width, size.height, format) });
  });
  const textureBytes = images.reduce((sum, entry) => sum + entry.bytes, 0);
  return { textureBytes, meshBytes: analysis.accessorBytes, totalBytes: textureBytes + analysis.accessorBytes, images };
}
