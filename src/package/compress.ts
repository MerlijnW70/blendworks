import { availableParallelism } from "node:os";
import { blenderJobs, blenderThreads } from "../blender.js";
import type { Limits, Tools } from "../judge/sandbox.js";
import { compressionArguments, type PackResult } from "./gltfpack.js";
import type { Ktx2Status } from "./report.js";
import type { ColourQuality } from "./textures.js";
import { selectGltfpack, type GltfpackInfo, type SelectOptions } from "./tool.js";

export type Compression = {
  output: Uint8Array;
  arguments: string[];
  gltfpack: GltfpackInfo;
  ktx2: { requested: boolean; status: Ktx2Status; reason: string | null };
};

export type CompressOptions = {
  meshopt: boolean;
  ktx2: boolean;
  hasImages: boolean;
  colourQuality?: ColourQuality;
  sandbox?: { limits: Limits; tools: Tools };
  select?: SelectOptions;
};

export async function compress(input: Uint8Array, options: CompressOptions): Promise<Compression> {
  const tool = await selectGltfpack({ ...options.select, ...(options.sandbox === undefined ? {} : { limits: options.sandbox.limits, tools: options.sandbox.tools }) });
  const support = { ktx2: tool.info.ktx2, reason: tool.info.ktx2Reason };
  const threads = blenderThreads(blenderJobs(), availableParallelism());
  const args = compressionArguments({ meshopt: options.meshopt, ktx2: options.ktx2, ...(options.colourQuality === undefined ? {} : { colourQuality: options.colourQuality }), threads }, support);
  const packed: PackResult = await tool.run(input, args);
  let status: Ktx2Status = "not requested";
  let reason: string | null = null;
  if (options.ktx2 && !support.ktx2) {
    status = "unavailable";
    const native = tool.info.nativeSkipped === null ? "" : `; ${tool.info.nativeSkipped}`;
    reason = `${(support.reason ?? "the encoder is missing").replace(/^Error: /, "")}${native}; the textures are copied unchanged`;
  } else if (options.ktx2) {
    status = options.hasImages ? "written" : "no textures";
  }
  return { output: packed.output, arguments: args, gltfpack: tool.info, ktx2: { requested: options.ktx2, status, reason } };
}
