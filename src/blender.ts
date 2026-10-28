import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { availableParallelism, homedir, platform } from "node:os";
import { posix, win32 } from "node:path";

export const BLENDER_VERSION = "5.2";
export const BLENDER_DOWNLOAD_URL = "https://www.blender.org/download/lts/";
export const BLENDER_VARIABLE = "BLENDER";
export const JOBS_VARIABLE = "BLENDWORKS_JOBS";
export const DEFAULT_JOBS = 2;

export type BlenderSource = "BLENDER" | "default location" | "PATH";

export type BlenderLookup = {
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  home?: string;
  exists?: (path: string) => boolean;
};

export type ResolvedBlender = { path: string; source: BlenderSource };

export class BlenderNotFoundError extends Error {
  readonly reason: string;
  readonly tried: string[];

  constructor(message: string, reason: string = message, tried: string[] = []) {
    super(message);
    this.name = "BlenderNotFoundError";
    this.reason = reason;
    this.tried = tried;
  }
}

function pathRules(os: NodeJS.Platform): typeof posix {
  return os === "win32" ? win32 : posix;
}

export function defaultBlenderLocations(os: NodeJS.Platform, env: NodeJS.ProcessEnv, home: string): string[] {
  const { join } = pathRules(os);
  if (os === "win32") {
    const programFiles = env["ProgramFiles"] ?? "C:\\Program Files";
    const local = env["LOCALAPPDATA"] ?? join(home, "AppData", "Local");
    return [
      join(programFiles, "Blender Foundation", `Blender ${BLENDER_VERSION}`, "blender.exe"),
      join(local, "Programs", "Blender Foundation", `Blender ${BLENDER_VERSION}`, "blender.exe"),
      join(home, "tools", "blender", "blender.exe"),
    ];
  }
  if (os === "darwin") return ["/Applications/Blender.app/Contents/MacOS/Blender", join(home, "Applications", "Blender.app", "Contents", "MacOS", "Blender")];
  return [join(home, "tools", "blender", "blender"), join(home, "blender", "blender"), "/opt/blender/blender", "/usr/local/bin/blender", "/usr/bin/blender", "/snap/bin/blender"];
}

function onPath(name: string, os: NodeJS.Platform, env: NodeJS.ProcessEnv, exists: (path: string) => boolean): string | undefined {
  const { delimiter, join } = pathRules(os);
  const file = os === "win32" && !/\.exe$/i.test(name) ? `${name}.exe` : name;
  const folders = (env["PATH"] ?? env["Path"] ?? "").split(delimiter).filter((folder) => folder !== "");
  return folders.map((folder) => join(folder, file)).find((candidate) => exists(candidate));
}

function notFound(reason: string, tried: string[]): BlenderNotFoundError {
  const lines = [reason];
  if (tried.length > 0) lines.push("Looked at:", ...tried.map((path) => `  ${path}`));
  lines.push(`Download Blender ${BLENDER_VERSION} from ${BLENDER_DOWNLOAD_URL} and set ${BLENDER_VARIABLE} to the blender binary.`);
  return new BlenderNotFoundError(lines.join("\n"), reason, tried);
}

export function resolveBlender(lookup: BlenderLookup = {}): ResolvedBlender {
  const env = lookup.env ?? process.env;
  const os = lookup.platform ?? platform();
  const exists = lookup.exists ?? existsSync;
  const requested = env[BLENDER_VARIABLE];
  if (requested !== undefined && requested !== "") {
    const rules = pathRules(os);
    if (rules.isAbsolute(requested) || requested.includes("/") || requested.includes(rules.sep)) {
      if (exists(requested)) return { path: requested, source: "BLENDER" };
      throw notFound(`${BLENDER_VARIABLE} is set to ${requested}, which does not exist.`, []);
    }
    const found = onPath(requested, os, env, exists);
    if (found !== undefined) return { path: found, source: "BLENDER" };
    throw notFound(`${BLENDER_VARIABLE} is set to ${requested}, which is not on PATH.`, []);
  }
  const defaults = defaultBlenderLocations(os, env, lookup.home ?? homedir());
  const known = defaults.find((candidate) => exists(candidate));
  if (known !== undefined) return { path: known, source: "default location" };
  const found = onPath("blender", os, env, exists);
  if (found !== undefined) return { path: found, source: "PATH" };
  throw notFound(`Blender was not found and ${BLENDER_VARIABLE} is not set.`, defaults);
}

export function blenderPath(): string {
  return resolveBlender().path;
}

export function blenderVersionOutput(blender: string): string {
  try {
    return execFileSync(blender, ["--background", "--factory-startup", "--version"], { encoding: "utf8", timeout: 60_000, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  } catch (error) {
    throw new BlenderNotFoundError(`cannot run Blender at ${blender}: ${(error as Error).message.split("\n")[0]}`);
  }
}

export function blenderJobs(env: NodeJS.ProcessEnv = process.env): number {
  const text = env[JOBS_VARIABLE];
  if (text === undefined || text.trim() === "") return DEFAULT_JOBS;
  if (!/^\d+$/.test(text.trim()) || Number(text) < 1) throw new Error(`${JOBS_VARIABLE} must be a whole number of at least 1, not "${text}"`);
  return Number(text);
}

export function blenderThreads(jobs: number, cpus: number = availableParallelism()): number {
  return Math.max(1, Math.floor(cpus / Math.max(1, jobs)));
}

export function blenderThreadArguments(jobs: number = blenderJobs(), cpus: number = availableParallelism()): string[] {
  return ["--threads", String(blenderThreads(jobs, cpus))];
}
