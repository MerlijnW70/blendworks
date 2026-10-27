import { createRequire } from "node:module";
import { GLTFPACK_PACKAGE, compressionArguments, probeTextureSupport, runGltfpack, type PackResult } from "./gltfpack.js";
import type { Ktx2Status } from "./report.js";

export type Compression = { output: Uint8Array; arguments: string[]; ktx2: { requested: boolean; status: Ktx2Status; reason: string | null } };

export function gltfpackVersion(): string {
  return (createRequire(import.meta.url)(`${GLTFPACK_PACKAGE}/package.json`) as { version: string }).version;
}

export async function compress(input: Uint8Array, options: { meshopt: boolean; ktx2: boolean; hasImages: boolean }): Promise<Compression> {
  const support = await probeTextureSupport();
  const args = compressionArguments({ meshopt: options.meshopt, ktx2: options.ktx2 }, support);
  const packed: PackResult = await runGltfpack(input, args);
  let status: Ktx2Status = "not requested";
  let reason: string | null = null;
  if (options.ktx2 && !support.ktx2) {
    status = "unavailable";
    reason = `${(support.reason ?? "the encoder is missing").replace(/^Error: /, "")}; the textures are copied unchanged`;
  } else if (options.ktx2) {
    status = options.hasImages ? "written" : "no textures";
  }
  return { output: packed.output, arguments: args, ktx2: { requested: options.ktx2, status, reason } };
}
