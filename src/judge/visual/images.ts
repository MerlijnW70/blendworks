import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { decodePng, downscale, encodePng, fitWithin } from "./png.js";

export const IMAGE_CAP = 1024;
export const MAX_IMAGES = 20;
export const EVIDENCE_FOLDER = "visual";

export type EvidenceSource = { name: string; kind: "view" | "closeup"; path: string };

export type EvidenceImage = {
  name: string;
  kind: "view" | "closeup";
  caption: string;
  file: string;
  sourceSha256: string;
  sourceWidth: number;
  sourceHeight: number;
  width: number;
  height: number;
  bytes: number;
  sha256: string;
};

export type Evidence = { images: EvidenceImage[]; data: Buffer[] };

export function sha256Of(data: Buffer | string): string {
  return createHash("sha256").update(data).digest("hex");
}

function caption(source: EvidenceSource, index: number, total: number): string {
  const what = source.kind === "view" ? `the ${source.name} view` : `the ${source.name} close-up`;
  return `Image ${index + 1} of ${total}: ${what}, rendered by the judge.`;
}

export function prepareEvidence(sources: EvidenceSource[], outDir: string, cap: number = IMAGE_CAP): Evidence {
  if (sources.length === 0) throw new Error("no rendered images to send");
  if (sources.length > MAX_IMAGES) throw new Error(`${sources.length} images, at most ${MAX_IMAGES}`);
  const folder = join(outDir, EVIDENCE_FOLDER);
  mkdirSync(folder, { recursive: true });
  const images: EvidenceImage[] = [];
  const data: Buffer[] = [];
  sources.forEach((source, index) => {
    if (!/^[a-z0-9-]{1,40}$/.test(source.name)) throw new Error(`the image name ${JSON.stringify(source.name)} is not a judge name`);
    const original = readFileSync(source.path);
    const decoded = decodePng(original);
    const size = fitWithin(decoded.width, decoded.height, cap);
    const encoded = encodePng(downscale(decoded, size.width, size.height));
    const file = `${EVIDENCE_FOLDER}/${source.kind}-${source.name}.png`;
    writeFileSync(join(outDir, file), encoded);
    data.push(encoded);
    images.push({
      name: source.name,
      kind: source.kind,
      caption: caption(source, index, sources.length),
      file,
      sourceSha256: sha256Of(original),
      sourceWidth: decoded.width,
      sourceHeight: decoded.height,
      width: size.width,
      height: size.height,
      bytes: encoded.length,
      sha256: sha256Of(encoded),
    });
  });
  return { images, data };
}
