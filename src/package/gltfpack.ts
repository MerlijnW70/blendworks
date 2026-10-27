import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { Worker } from "node:worker_threads";
import { tinyTexturedGlb } from "./tiny.js";

export const GLTFPACK_PACKAGE = "gltfpack";
export const GLTFPACK_LIMITS = { heapMb: 2048, timeoutMs: 300_000 };
export const INPUT_NAME = "input.glb";
export const OUTPUT_NAME = "output.glb";

export class GltfpackError extends Error {
  constructor(
    readonly code: "failed" | "timeout" | "crashed",
    message: string,
  ) {
    super(message);
    this.name = "GltfpackError";
  }
}

export type PackResult = { output: Uint8Array; log: string };

export type TextureSupport = { ktx2: boolean; reason: string | null };

const WORKER = `
const { parentPort, workerData } = require("node:worker_threads");
const files = new Map([[workerData.inputName, new Uint8Array(workerData.input)]]);
const written = new Map();
const iface = {
  read(path) {
    const data = files.get(path);
    if (data === undefined) throw new Error("gltfpack asked for a file the judge does not provide: " + path);
    return data;
  },
  write(path, data) {
    written.set(path, new Uint8Array(data));
  },
};
import(workerData.libraryUrl)
  .then((library) => library.pack(workerData.args, iface))
  .then(
    (log) => {
      const output = written.get(workerData.outputName);
      if (output === undefined) return parentPort.postMessage({ kind: "failed", message: "gltfpack wrote no output" });
      parentPort.postMessage({ kind: "done", log, output }, [output.buffer]);
    },
    (error) => parentPort.postMessage({ kind: "failed", message: String(error && error.message ? error.message : error) }),
  );
`;

export function libraryUrl(): string {
  return pathToFileURL(createRequire(import.meta.url).resolve(`${GLTFPACK_PACKAGE}/library.js`)).href;
}

export async function runGltfpack(input: Uint8Array, args: string[], limits = GLTFPACK_LIMITS): Promise<PackResult> {
  const copy = input.slice();
  const worker = new Worker(WORKER, {
    eval: true,
    workerData: { libraryUrl: libraryUrl(), input: copy.buffer, inputName: INPUT_NAME, outputName: OUTPUT_NAME, args: ["-i", INPUT_NAME, "-o", OUTPUT_NAME, ...args] },
    transferList: [copy.buffer],
    resourceLimits: { maxOldGenerationSizeMb: limits.heapMb },
    stdout: true,
    stderr: true,
  });
  worker.stdout.resume();
  worker.stderr.resume();
  try {
    return await new Promise<PackResult>((resolve, reject) => {
      const timer = setTimeout(() => reject(new GltfpackError("timeout", `gltfpack took longer than ${limits.timeoutMs / 1000} s and was stopped`)), limits.timeoutMs);
      const settle = (action: () => void) => {
        clearTimeout(timer);
        action();
      };
      worker.on("message", (message: { kind: string; log?: string; output?: Uint8Array; message?: string }) => {
        if (message.kind === "done" && message.output !== undefined) return settle(() => resolve({ output: message.output!, log: message.log ?? "" }));
        settle(() => reject(new GltfpackError("failed", (message.message ?? "gltfpack failed").slice(0, 600))));
      });
      worker.on("error", (error: Error) => settle(() => reject(new GltfpackError("crashed", `gltfpack stopped: ${error.message.slice(0, 400)}`))));
      worker.on("exit", (code) => settle(() => reject(new GltfpackError("crashed", `gltfpack exited with code ${code} before it finished`))));
    });
  } finally {
    await worker.terminate();
  }
}

let probed: Promise<TextureSupport> | undefined;

export function probeTextureSupport(): Promise<TextureSupport> {
  probed ??= (async () => {
    try {
      await runGltfpack(tinyTexturedGlb(), ["-tc"]);
      return { ktx2: true, reason: null };
    } catch (error) {
      if (!(error instanceof GltfpackError)) throw error;
      return { ktx2: false, reason: error.message.split("\n")[0] ?? error.message };
    }
  })();
  return probed;
}

export const TEXTURE_CLASSES = ["color", "normal", "attrib"] as const;
export type TextureClass = (typeof TEXTURE_CLASSES)[number];
export const TEXTURE_QUALITY: Record<TextureClass, number> = { color: 8, normal: 8, attrib: 8 };
export const UASTC_CLASSES: Record<"compact" | "high", readonly TextureClass[]> = { compact: ["normal", "attrib"], high: ["color", "normal", "attrib"] };

export type CompressOptions = { meshopt: boolean; ktx2: boolean; colourQuality?: "compact" | "high"; threads?: number };

export function textureArguments(colourQuality: "compact" | "high", threads?: number): string[] {
  const args = ["-tc", "-tu", UASTC_CLASSES[colourQuality].join(",")];
  for (const textureClass of TEXTURE_CLASSES) args.push("-tq", textureClass, String(TEXTURE_QUALITY[textureClass]));
  if (threads !== undefined) args.push("-tj", String(threads));
  return args;
}

export function compressionArguments(options: CompressOptions, support: TextureSupport): string[] {
  const args = ["-kn", "-km", "-ke"];
  if (options.meshopt) args.push("-cc");
  if (options.ktx2 && support.ktx2) args.push(...textureArguments(options.colourQuality ?? "compact", options.threads));
  return args;
}
