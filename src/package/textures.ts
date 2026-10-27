import type { ValidationInfo } from "../judge/validator.js";
import type { Analysis, TextureSlot } from "./analysis.js";
import type { GlbParts } from "./glb.js";
import { Ktx2Error, parseKtx2, type Ktx2Codec, type Ktx2Info, type Ktx2Transfer } from "./ktx2.js";

export const KTX2_MIME_TYPE = "image/ktx2";
export const BASISU_EXTENSION = "KHR_texture_basisu";

export type ImageDetail = {
  index: number;
  mimeType: string;
  width: number | null;
  height: number | null;
  ktx2: Ktx2Info | null;
  error: string | null;
};

export type ColourQuality = "compact" | "high";

export type TexturePlan = { ktx2: boolean; colourQuality: ColourQuality };

const COLOUR_SLOTS: readonly TextureSlot[] = ["baseColor", "emissive"];

export function isColourSlot(slot: TextureSlot): boolean {
  return COLOUR_SLOTS.includes(slot);
}

export function expectedCodec(slot: TextureSlot, colourQuality: ColourQuality): Ktx2Codec {
  return isColourSlot(slot) && colourQuality === "compact" ? "etc1s" : "uastc";
}

export function expectedTransfer(slot: TextureSlot): Ktx2Transfer {
  return isColourSlot(slot) ? "srgb" : "linear";
}

function imageBytes(parts: GlbParts, bufferView: number | null): Uint8Array {
  const view = bufferView === null ? undefined : (parts.json.bufferViews as { buffer?: number; byteOffset?: number; byteLength?: number }[] | undefined)?.[bufferView];
  if (view === undefined) throw new Ktx2Error("the image has no buffer view");
  if ((view.buffer ?? 0) !== 0 || parts.bin === null) throw new Ktx2Error("the image data is not in the binary chunk");
  const start = view.byteOffset ?? 0;
  const length = view.byteLength ?? 0;
  if (start < 0 || length < 0 || start + length > parts.bin.byteLength) throw new Ktx2Error("the image data runs past the binary chunk");
  return parts.bin.subarray(start, start + length);
}

function validatorSizes(info: ValidationInfo): Map<number, { width: number; height: number }> {
  const sizes = new Map<number, { width: number; height: number }>();
  for (const resource of info.resources ?? []) {
    const match = /^\/images\/(\d+)$/.exec(resource.pointer);
    if (match !== null && resource.image?.width !== undefined && resource.image.height !== undefined) {
      sizes.set(Number(match[1]), { width: resource.image.width, height: resource.image.height });
    }
  }
  return sizes;
}

export function readImages(parts: GlbParts, analysis: Analysis, info: ValidationInfo): ImageDetail[] {
  const sizes = validatorSizes(info);
  return analysis.images.map((image, index): ImageDetail => {
    if (image.mimeType !== KTX2_MIME_TYPE) {
      const size = sizes.get(index);
      return { index, mimeType: image.mimeType, width: size?.width ?? null, height: size?.height ?? null, ktx2: null, error: null };
    }
    try {
      const ktx2 = parseKtx2(imageBytes(parts, image.bufferView));
      return { index, mimeType: image.mimeType, width: ktx2.width, height: ktx2.height, ktx2, error: null };
    } catch (error) {
      if (!(error instanceof Ktx2Error)) throw error;
      return { index, mimeType: image.mimeType, width: null, height: null, ktx2: null, error: `image ${index}: ${error.message}` };
    }
  });
}
