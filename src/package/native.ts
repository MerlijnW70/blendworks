import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { resolveBlender } from "../blender.js";
import { detectTools, type Limits, type Tools } from "../judge/sandbox.js";
import { GLTFPACK_RELEASE, platformKey, type ReleasePin } from "./gltfpack-release.js";
import { INPUT_NAME, OUTPUT_NAME, type TextureSupport } from "./gltfpack.js";
import { INSTALL_COMMAND, cacheRoot, lookupInstalled, sha256Of } from "./native-install.js";
import { runNative, type NativeRunner } from "./native-run.js";
import { tinyTexturedGlb } from "./tiny.js";

export const GLTFPACK_VARIABLE = "BLENDWORKS_GLTFPACK";
export const NATIVE_LIMITS: Limits = { timeoutMs: 300_000, memoryBytes: 4096 * 1024 * 1024 };
const PROBE_LIMITS: Limits = { timeoutMs: 60_000, memoryBytes: 1024 * 1024 * 1024 };

export type NativeSource = "installed" | typeof GLTFPACK_VARIABLE;

export type NativeFacts = { version: string; ktx2: TextureSupport };

export type NativeTool = NativeFacts & { path: string; source: NativeSource; sha256: string };

export type NativeSelection = { tool: NativeTool; reason: null } | { tool: null; reason: string };

export type NativeContext = {
  env?: NodeJS.ProcessEnv;
  root?: string;
  pin?: ReleasePin;
  key?: string;
  tools?: Tools;
  runner?: NativeRunner;
};

const facts = new WeakMap<NativeRunner, Map<string, Promise<NativeFacts | string>>>();

export function defaultTools(): Tools {
  try {
    return detectTools(resolveBlender().path);
  } catch {
    return detectTools();
  }
}

function firstLine(text: string, fallback: string): string {
  const line = text
    .split(/\r?\n/)
    .map((entry) => entry.trim())
    .find((entry) => entry.length > 0);
  return (line ?? fallback).slice(0, 300);
}

async function interrogate(path: string, pin: ReleasePin, tools: Tools, runner: NativeRunner): Promise<NativeFacts | string> {
  let versionRun;
  try {
    versionRun = await runner({ binary: path, args: ["-v"], limits: PROBE_LIMITS, tools });
  } catch (error) {
    return `${path} could not be started: ${(error as Error).message.split("\n")[0]}`;
  }
  const match = /^gltfpack (\S+)\s*$/m.exec(versionRun.log);
  if (versionRun.code !== 0 || match === null) return `${path} did not answer "gltfpack ${pin.version}" to -v (${firstLine(versionRun.log, `exit code ${versionRun.code}`)})`;
  if (match[1] !== pin.version) return `${path} is gltfpack ${match[1]}, but the judge is verified for gltfpack ${pin.version}`;
  const probe = await runner({
    binary: path,
    args: ["-i", INPUT_NAME, "-o", OUTPUT_NAME, "-tc"],
    limits: PROBE_LIMITS,
    tools,
    input: { name: INPUT_NAME, data: tinyTexturedGlb() },
    output: OUTPUT_NAME,
  });
  const ktx2: TextureSupport = probe.code === 0 && probe.output !== null ? { ktx2: true, reason: null } : { ktx2: false, reason: firstLine(probe.log, `exit code ${probe.code}`) };
  return { version: match[1], ktx2 };
}

export async function selectNative(context: NativeContext = {}): Promise<NativeSelection> {
  const env = context.env ?? process.env;
  const pin = context.pin ?? GLTFPACK_RELEASE;
  const key = context.key ?? platformKey();
  const runner = context.runner ?? runNative;
  const requested = env[GLTFPACK_VARIABLE];
  let path: string;
  let source: NativeSource;
  if (requested !== undefined && requested !== "") {
    path = resolve(requested);
    source = GLTFPACK_VARIABLE;
    try {
      if (!statSync(path).isFile()) return { tool: null, reason: `${GLTFPACK_VARIABLE} names ${path}, which is not a file` };
    } catch {
      return { tool: null, reason: `${GLTFPACK_VARIABLE} names ${path}, which does not exist` };
    }
  } else {
    const found = lookupInstalled(context.root ?? cacheRoot(env), pin, key);
    if (found.state === "missing") return { tool: null, reason: `the native gltfpack is not installed (${INSTALL_COMMAND} installs it)` };
    if (found.state === "corrupt") {
      return { tool: null, reason: `the installed gltfpack at ${found.path} had sha256 ${found.actual}, which is not the pinned one; it was deleted (${INSTALL_COMMAND} installs it again)` };
    }
    path = found.path;
    source = "installed";
  }
  const sha256 = sha256Of(readFileSync(path));
  const tools = context.tools ?? defaultTools();
  const memo = facts.get(runner) ?? new Map<string, Promise<NativeFacts | string>>();
  facts.set(runner, memo);
  const memoKey = `${path}\0${sha256}\0${pin.version}\0${tools.platform}\0${tools.lowIntegrityPython ?? ""}`;
  let pending = memo.get(memoKey);
  if (pending === undefined) {
    pending = interrogate(path, pin, tools, runner);
    memo.set(memoKey, pending);
  }
  const outcome = await pending;
  if (typeof outcome === "string") return { tool: null, reason: outcome };
  return { tool: { ...outcome, path, source, sha256 }, reason: null };
}
