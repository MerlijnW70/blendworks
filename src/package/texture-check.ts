import { TEXTURE_SLOTS, type Analysis, type MaterialInfo, type TextureSlot } from "./analysis.js";
import { fullMipCount, type Ktx2Info } from "./ktx2.js";
import { BASISU_EXTENSION, KTX2_MIME_TYPE, expectedCodec, expectedTransfer, type ImageDetail, type TexturePlan } from "./textures.js";

export type TextureCheck = { name: "textures"; pass: boolean; detail: string };

export type TextureInput = { reference: Analysis; candidate: Analysis; referenceImages: ImageDetail[]; candidateImages: ImageDetail[]; plan: TexturePlan };

const LISTED = 5;

function listed(items: string[]): string {
  return items.length <= LISTED ? items.join("; ") : `${items.slice(0, LISTED).join("; ")}; and ${items.length - LISTED} more`;
}

function declarationProblems(candidate: Analysis, images: ImageDetail[]): string[] {
  const ktx2 = images.filter((image) => image.mimeType === KTX2_MIME_TYPE);
  if (ktx2.length === 0) return [];
  const problems: string[] = [];
  if (!candidate.extensionsUsed.includes(BASISU_EXTENSION)) problems.push(`${BASISU_EXTENSION} is not in extensionsUsed`);
  if (!candidate.extensionsRequired.includes(BASISU_EXTENSION)) problems.push(`${BASISU_EXTENSION} is not in extensionsRequired`);
  const viaExtension = new Set(candidate.textures.flatMap((texture) => (texture.basisu === null ? [] : [texture.basisu])));
  const viaSource = new Set(candidate.textures.flatMap((texture) => (texture.source === null ? [] : [texture.source])));
  for (const image of ktx2) {
    if (!viaExtension.has(image.index)) problems.push(`image ${image.index} is KTX2 but no texture names it in ${BASISU_EXTENSION}`);
    if (viaSource.has(image.index)) problems.push(`image ${image.index} is KTX2 but a texture uses it as a plain source`);
  }
  return problems;
}

function ktx2Problems(label: string, slot: TextureSlot, header: Ktx2Info, plan: TexturePlan): string[] {
  const problems: string[] = [];
  const mips = fullMipCount(header.width, header.height);
  if (header.levelCount !== mips) problems.push(`${label} has ${header.levelCount} mip levels, a ${header.width} by ${header.height} image needs ${mips}`);
  const codec = expectedCodec(slot, plan.colourQuality);
  if (header.codec !== codec) problems.push(`${label} is ${header.codec.toUpperCase()}, a ${slot} map must be ${codec.toUpperCase()}`);
  const transfer = expectedTransfer(slot);
  if (header.transfer !== transfer) problems.push(`${label} is ${header.transfer}, a ${slot} map must be ${transfer}`);
  return problems;
}

function slotProblems(material: MaterialInfo, other: MaterialInfo, input: TextureInput): string[] {
  const problems: string[] = [];
  for (const slot of TEXTURE_SLOTS) {
    const source = material.slots[slot];
    const target = other.slots[slot];
    if (source === undefined || target === undefined || source.image === null || target.image === null) continue;
    const label = `${material.name} ${slot} map`;
    const before = input.referenceImages[source.image];
    const after = input.candidateImages[target.image];
    if (before === undefined || after === undefined) {
      problems.push(`${label} points at an image that does not exist`);
      continue;
    }
    if (after.error !== null) continue;
    if (before.width === null || before.height === null) problems.push(`${label} has a source image of unknown size`);
    else if (after.width !== before.width || after.height !== before.height) problems.push(`${label} is ${after.width} by ${after.height}, was ${before.width} by ${before.height}`);
    if (input.plan.ktx2) {
      if (after.ktx2 === null) problems.push(`${label} is not KTX2`);
      else problems.push(...ktx2Problems(label, slot, after.ktx2, input.plan));
    }
  }
  return problems;
}

export function textureCheck(input: TextureInput): TextureCheck {
  const { reference, candidate, candidateImages } = input;
  const problems: string[] = [];
  for (const image of candidateImages) if (image.error !== null) problems.push(image.error);
  if (reference.textures.length !== candidate.textures.length) problems.push(`${reference.textures.length} textures against ${candidate.textures.length}`);
  const others = new Map(candidate.materials.map((material) => [material.name, material]));
  let slots = 0;
  for (const material of reference.materials) {
    const other = others.get(material.name);
    if (other === undefined) continue;
    slots += TEXTURE_SLOTS.filter((slot) => material.slots[slot]?.image !== undefined && material.slots[slot]?.image !== null).length;
    problems.push(...slotProblems(material, other, input));
  }
  problems.push(...declarationProblems(candidate, candidateImages));
  const kind = input.plan.ktx2 ? "KTX2 with the right codec, colour space and a full mip chain" : "same size";
  return { name: "textures", pass: problems.length === 0, detail: problems.length === 0 ? `${slots} texture slots in ${candidate.images.length} images, ${kind}` : listed(problems) };
}
