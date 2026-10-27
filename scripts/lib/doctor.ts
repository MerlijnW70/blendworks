import { accessSync, constants, readdirSync, statSync } from "node:fs";
import { availableParallelism } from "node:os";
import { join } from "node:path";
import { BLENDER_DOWNLOAD_URL, BLENDER_VERSION, BlenderNotFoundError, blenderJobs, blenderThreads, resolveBlender } from "../../src/blender.js";
import { DEVICE_VARIABLE, GPU_BACKENDS, parseDeviceMode } from "../../src/judge/device.js";
import { detectTools, type Tools } from "../../src/judge/sandbox.js";
import { GLTFPACK_RELEASE, platformKey } from "../../src/package/gltfpack-release.js";
import { INSTALL_COMMAND } from "../../src/package/native-install.js";
import { GLTFPACK_VARIABLE, selectNative } from "../../src/package/native.js";
import { checkedBlender } from "./blender-check.js";
import { FIXTURE_FOLDER, fixtureKey, fixtureSets } from "./fixtures.js";
import { isComplete, entryDirectory } from "./entry-cache.js";
import { cacheRoot, CACHE_VARIABLE, ensureCacheRoot } from "./paths.js";
import { runBlender } from "./run.js";
import { activeSlots } from "./slots.js";

export type Status = "ok" | "warn" | "fail";

export type Finding = { status: Status; label: string; detail: string; fix?: string };

export const NODE_RANGE = "^22.12.0 || ^24.0.0 || >=26.0.0";

export function nodeSupported(version: string): boolean {
  const [major = 0, minor = 0] = version.replace(/^v/, "").split(".").map(Number);
  if (major === 22) return minor >= 12;
  return major === 24 || major >= 26;
}

const DEVICE_SCRIPT = `
import bpy, json
preferences = bpy.context.preferences.addons["cycles"].preferences
found = {}
for backend in ${JSON.stringify(GPU_BACKENDS)}:
    try:
        preferences.compute_device_type = backend
    except TypeError:
        continue
    preferences.refresh_devices()
    names = [device.name for device in preferences.devices if device.type == backend]
    if names:
        found[backend] = names
print("DEVICES" + json.dumps(found))
`;

export function parseDevices(output: string): Record<string, string[]> | undefined {
  const line = output.split(/\r?\n/).find((text) => text.startsWith("DEVICES"));
  if (line === undefined) return undefined;
  try {
    return JSON.parse(line.slice("DEVICES".length)) as Record<string, string[]>;
  } catch {
    return undefined;
  }
}

function checkNode(): Finding {
  const version = process.versions.node;
  if (nodeSupported(version)) return { status: "ok", label: "Node", detail: version };
  return { status: "fail", label: "Node", detail: `${version} is not supported (needs ${NODE_RANGE})`, fix: "install a current Node LTS from https://nodejs.org/" };
}

async function checkBlender(env: NodeJS.ProcessEnv, root: string): Promise<{ findings: Finding[]; path?: string; version?: string }> {
  let resolved;
  try {
    resolved = resolveBlender({ env });
  } catch (error) {
    if (!(error instanceof BlenderNotFoundError)) throw error;
    const looked = error.tried.length > 0 ? ` (looked at ${error.tried.join("; ")})` : "";
    return { findings: [{ status: "fail", label: "Blender", detail: error.reason, fix: `download Blender ${BLENDER_VERSION} from ${BLENDER_DOWNLOAD_URL} and set BLENDER to the blender binary${looked}` }] };
  }
  try {
    const checked = checkedBlender(root, resolved);
    return { findings: [{ status: "ok", label: "Blender", detail: `${checked.version} at ${checked.path} (from ${checked.source})` }], path: checked.path, version: checked.version };
  } catch (error) {
    return {
      findings: [{ status: "fail", label: "Blender", detail: (error as Error).message.split("\n")[0] ?? "unusable", fix: `install Blender ${BLENDER_VERSION} from ${BLENDER_DOWNLOAD_URL} and set BLENDER to its binary` }],
    };
  }
}

async function checkDevices(env: NodeJS.ProcessEnv, root: string, blender: string | undefined): Promise<Finding[]> {
  const findings: Finding[] = [];
  let mode;
  try {
    mode = parseDeviceMode(env[DEVICE_VARIABLE]);
  } catch (error) {
    return [{ status: "fail", label: DEVICE_VARIABLE, detail: (error as Error).message, fix: `set ${DEVICE_VARIABLE} to auto, gpu or cpu, or unset it` }];
  }
  findings.push({ status: "ok", label: DEVICE_VARIABLE, detail: `${mode}${env[DEVICE_VARIABLE] === undefined ? " (default)" : ""}` });
  if (blender === undefined) return findings;
  const result = await runBlender(blender, ["--background", "--factory-startup", "--python-expr", DEVICE_SCRIPT], { root, timeoutMs: 120_000 });
  const devices = parseDevices(result.stdout);
  if (devices === undefined) {
    findings.push({ status: "warn", label: "GPU devices", detail: "could not list the Cycles devices", fix: "run Blender once by hand to see why" });
    return findings;
  }
  const backends = Object.entries(devices);
  if (backends.length === 0) {
    const status = mode === "gpu" ? "fail" : "ok";
    findings.push({
      status,
      label: "GPU devices",
      detail: "none found; renders use the CPU",
      ...(mode === "gpu" ? { fix: `install a GPU driver Blender supports, or set ${DEVICE_VARIABLE}=auto or cpu` } : {}),
    });
    return findings;
  }
  findings.push({ status: "ok", label: "GPU devices", detail: backends.map(([backend, names]) => `${backend}: ${names.join(", ")}`).join("; ") });
  return findings;
}

function checkJobs(env: NodeJS.ProcessEnv): Finding {
  try {
    const jobs = blenderJobs(env);
    return { status: "ok", label: "BLENDWORKS_JOBS", detail: `${jobs} Blender process${jobs === 1 ? "" : "es"} at once, ${blenderThreads(jobs, availableParallelism())} threads each` };
  } catch (error) {
    return { status: "fail", label: "BLENDWORKS_JOBS", detail: (error as Error).message, fix: "set BLENDWORKS_JOBS to a whole number of at least 1, or unset it" };
  }
}

export function sandboxFindings(tools: Tools): Finding[] {
  if (tools.platform === "win32") {
    return [{ status: "ok", label: "Judge sandbox", detail: "Windows job object (memory and time caps); no network isolation, so judge untrusted assets in WSL or Linux" }];
  }
  if (tools.platform !== "linux") return [{ status: "warn", label: "Judge sandbox", detail: `${tools.platform} has no network or memory isolation`, fix: "judge untrusted assets on Linux or WSL" }];
  const findings: Finding[] = [];
  findings.push(
    tools.unshare
      ? { status: "ok", label: "unshare", detail: "network isolation works" }
      : { status: "warn", label: "unshare", detail: "unshare -rn does not work, so the judge cannot cut the network", fix: "install util-linux, and in WSL or a container allow unprivileged user namespaces" },
  );
  findings.push(
    tools.prlimit
      ? { status: "ok", label: "prlimit", detail: "memory caps work" }
      : { status: "warn", label: "prlimit", detail: "prlimit is missing, so the memory cap falls back to setrlimit", fix: "install util-linux" },
  );
  return findings;
}

function folderBytes(path: string): number {
  let total = 0;
  for (const entry of readdirSync(path, { withFileTypes: true })) {
    const full = join(path, entry.name);
    total += entry.isDirectory() ? folderBytes(full) : statSync(full).size;
  }
  return total;
}

export function checkCache(root: string, blenderVersion: string | undefined): Finding[] {
  const findings: Finding[] = [];
  try {
    ensureCacheRoot(root);
    accessSync(root, constants.W_OK);
  } catch (error) {
    return [{ status: "fail", label: "Cache", detail: `${root} is not writable: ${(error as Error).message}`, fix: `make it writable or point ${CACHE_VARIABLE} at a folder you own` }];
  }
  const megabytes = Math.round(folderBytes(root) / (1024 * 1024));
  findings.push({ status: "ok", label: "Cache", detail: `${root} (${megabytes} MB; npm run clean empties it)` });
  if (blenderVersion !== undefined) {
    const missing = fixtureSets().filter((set) => !isComplete(entryDirectory(root, `${FIXTURE_FOLDER}/${set.name}`, fixtureKey(set.script, blenderVersion))));
    findings.push(
      missing.length === 0
        ? { status: "ok", label: "Judge fixtures", detail: "cached" }
        : { status: "ok", label: "Judge fixtures", detail: `not generated yet (${missing.map((set) => set.name).join(", ")}); npm test or npm run fixtures makes them once` },
    );
  }
  const busy = activeSlots(root);
  if (busy.length > 0) findings.push({ status: "ok", label: "Blender slots", detail: `${busy.length} in use by process ${busy.map((slot) => slot.pid).join(", ")}` });
  return findings;
}

export async function checkGltfpack(env: NodeJS.ProcessEnv, root: string, tools: Tools): Promise<Finding[]> {
  const selection = await selectNative({ env, root, tools });
  if (selection.tool === null) {
    const supported = GLTFPACK_RELEASE.platforms[platformKey()] !== undefined;
    return [
      {
        status: "warn",
        label: "gltfpack",
        detail: `${selection.reason}; packages use the npm build, which cannot write KTX2 textures`,
        fix: supported ? `run ${INSTALL_COMMAND}, or set ${GLTFPACK_VARIABLE} to a gltfpack ${GLTFPACK_RELEASE.version} binary` : `set ${GLTFPACK_VARIABLE} to a gltfpack ${GLTFPACK_RELEASE.version} binary built with BasisU (no pinned release for ${platformKey()})`,
      },
    ];
  }
  const { tool } = selection;
  if (!tool.ktx2.ktx2) {
    return [{ status: "warn", label: "gltfpack", detail: `native ${tool.version} at ${tool.path} cannot write KTX2 (${tool.ktx2.reason})`, fix: `run ${INSTALL_COMMAND}, or point ${GLTFPACK_VARIABLE} at a build with BasisU` }];
  }
  return [{ status: "ok", label: "gltfpack", detail: `native ${tool.version} at ${tool.path} (from ${tool.source}), sha256 ${tool.sha256.slice(0, 12)}, writes KTX2` }];
}

export async function runDoctor(env: NodeJS.ProcessEnv = process.env): Promise<Finding[]> {
  const root = cacheRoot(env);
  const findings: Finding[] = [checkNode()];
  const blender = await checkBlender(env, root);
  findings.push(...blender.findings);
  findings.push(checkJobs(env));
  findings.push(...(await checkDevices(env, root, blender.path)));
  const tools = blender.path === undefined ? detectTools() : detectTools(blender.path);
  findings.push(...sandboxFindings(tools));
  findings.push(...(await checkGltfpack(env, root, tools)));
  findings.push(...checkCache(root, blender.version));
  return findings;
}

export function formatFindings(findings: Finding[]): string[] {
  const lines: string[] = [];
  for (const finding of findings) {
    lines.push(`${finding.status.padEnd(4)}  ${finding.label}: ${finding.detail}`);
    if (finding.fix !== undefined) lines.push(`      fix: ${finding.fix}`);
  }
  const failed = findings.filter((finding) => finding.status === "fail").length;
  const warned = findings.filter((finding) => finding.status === "warn").length;
  lines.push(failed > 0 ? `${failed} problem${failed === 1 ? "" : "s"} to fix` : warned > 0 ? `ready, with ${warned} warning${warned === 1 ? "" : "s"}` : "ready");
  return lines;
}

export async function doctorMain(env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const findings = await runDoctor(env);
  for (const line of formatFindings(findings)) console.log(line);
  return findings.some((finding) => finding.status === "fail") ? 1 : 0;
}
