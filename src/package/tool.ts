import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import type { Limits, Tools } from "../judge/sandbox.js";
import { GLTFPACK_PACKAGE, GltfpackError, INPUT_NAME, OUTPUT_NAME, probeTextureSupport, runGltfpack, type PackResult, type TextureSupport } from "./gltfpack.js";
import { NATIVE_LIMITS, defaultTools, selectNative, type NativeContext, type NativeSource } from "./native.js";
import { planNative, runNative, type NativeRunner } from "./native-run.js";

const LOG_TAIL = 600;

export type GltfpackInfo = {
  kind: "native" | "npm";
  version: string;
  source: NativeSource | "npm package";
  sha256: string | null;
  ktx2: boolean;
  ktx2Reason: string | null;
  meshopt: boolean;
  nativeSkipped: string | null;
  isolation: { network: string; memory: string; filesystem: string } | null;
};

export type GltfpackTool = { info: GltfpackInfo; run(input: Uint8Array, args: string[]): Promise<PackResult> };

export type SelectOptions = NativeContext & { limits?: Limits };

export function npmGltfpackVersion(): string {
  return (createRequire(import.meta.url)(`${GLTFPACK_PACKAGE}/package.json`) as { version: string }).version;
}

function tail(text: string): string {
  const trimmed = text.trim();
  return trimmed.length <= LOG_TAIL ? trimmed : trimmed.slice(-LOG_TAIL);
}

function nativeRunner(path: string, runner: NativeRunner, tools: Tools, limits: Limits): GltfpackTool["run"] {
  return async (input, args) => {
    const result = await runner({
      binary: path,
      args: ["-i", INPUT_NAME, "-o", OUTPUT_NAME, ...args],
      limits,
      tools,
      input: { name: INPUT_NAME, data: input },
      output: OUTPUT_NAME,
    });
    if (result.timedOut) throw new GltfpackError("timeout", `gltfpack took longer than ${limits.timeoutMs / 1000} s and was stopped`);
    if (result.code === null) throw new GltfpackError("crashed", `gltfpack was stopped by ${result.signal ?? "the sandbox"}${result.log.trim() === "" ? "" : `: ${tail(result.log)}`}`);
    if (result.code !== 0) throw new GltfpackError("failed", tail(result.log) || `gltfpack exited with code ${result.code}`);
    if (result.output === null) throw new GltfpackError("failed", "gltfpack wrote no output");
    return { output: result.output, log: result.log };
  };
}

export async function selectGltfpack(options: SelectOptions = {}): Promise<GltfpackTool> {
  const tools = options.tools ?? defaultTools();
  const limits = options.limits ?? NATIVE_LIMITS;
  const runner = options.runner ?? runNative;
  const native = await selectNative({ ...options, tools, runner });
  if (native.tool !== null && native.tool.ktx2.ktx2) {
    const { tool } = native;
    const { network, memory, filesystem } = planNative(tool.path, [], limits, tools, tmpdir()).isolation;
    const info: GltfpackInfo = {
      kind: "native",
      version: tool.version,
      source: tool.source,
      sha256: tool.sha256,
      ktx2: true,
      ktx2Reason: null,
      meshopt: true,
      nativeSkipped: null,
      isolation: { network, memory, filesystem },
    };
    return { info, run: nativeRunner(tool.path, runner, tools, limits) };
  }
  const support: TextureSupport = await probeTextureSupport();
  const skipped = native.tool === null ? native.reason : `the native gltfpack at ${native.tool.path} was built without BasisU support (${native.tool.ktx2.reason ?? "no reason given"})`;
  const info: GltfpackInfo = {
    kind: "npm",
    version: npmGltfpackVersion(),
    source: "npm package",
    sha256: null,
    ktx2: support.ktx2,
    ktx2Reason: support.reason,
    meshopt: true,
    nativeSkipped: skipped,
    isolation: null,
  };
  return { info, run: (input, args) => runGltfpack(input, args) };
}
