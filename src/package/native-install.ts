import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { GLTFPACK_RELEASE, platformKey, type PlatformPin, type ReleasePin } from "./gltfpack-release.js";
import { readZipEntry } from "./zip.js";

export const CACHE_VARIABLE = "BLENDWORKS_CACHE";
export const INSTALL_COMMAND = "npm run tools:gltfpack";
const MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024;
const DOWNLOAD_TIMEOUT_MS = 120_000;

export type InstallErrorCode = "unsupported" | "download" | "hash" | "archive" | "write";

export class InstallError extends Error {
  constructor(
    readonly code: InstallErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "InstallError";
  }
}

export type Download = (url: string, maxBytes: number) => Promise<Uint8Array>;

export type InstallOptions = { root: string; pin?: ReleasePin; key?: string; download?: Download };

export type Installed = { path: string; status: "installed" | "already installed"; version: string; sha256: string };

export type InstalledLookup = { state: "ready"; path: string } | { state: "missing"; path: string } | { state: "corrupt"; path: string; actual: string };

export function repositoryRoot(): string {
  return resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
}

export function cacheRoot(env: NodeJS.ProcessEnv = process.env): string {
  const requested = env[CACHE_VARIABLE];
  return requested === undefined || requested === "" ? join(repositoryRoot(), ".cache") : resolve(requested);
}

export function sha256Of(data: Uint8Array): string {
  return createHash("sha256").update(data).digest("hex");
}

export function platformPin(pin: ReleasePin, key: string): PlatformPin {
  const found = pin.platforms[key];
  if (found === undefined) {
    throw new InstallError("unsupported", `gltfpack ${pin.version} has no pinned release for ${key}; it has ${Object.keys(pin.platforms).join(", ")}. Set BLENDWORKS_GLTFPACK to a gltfpack ${pin.version} binary you installed yourself`);
  }
  return found;
}

export function installedPath(root: string, pin: ReleasePin = GLTFPACK_RELEASE, key: string = platformKey()): string {
  return join(root, "tools", `gltfpack-${pin.version}`, key, platformPin(pin, key).executable);
}

export function lookupInstalled(root: string, pin: ReleasePin = GLTFPACK_RELEASE, key: string = platformKey()): InstalledLookup {
  const path = installedPath(root, pin, key);
  if (!existsSync(path)) return { state: "missing", path };
  const actual = sha256Of(readFileSync(path));
  if (actual === platformPin(pin, key).executableSha256) return { state: "ready", path };
  rmSync(path, { force: true });
  return { state: "corrupt", path, actual };
}

export async function fetchWithLimit(url: string, maxBytes: number): Promise<Uint8Array> {
  let response: Response;
  try {
    response = await fetch(url, { signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) });
  } catch (error) {
    throw new InstallError("download", `could not download ${url}: ${(error as Error).message}`);
  }
  if (!response.ok || response.body === null) throw new InstallError("download", `${url} answered ${response.status} ${response.statusText}`);
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for await (const chunk of response.body) {
      total += chunk.byteLength;
      if (total > maxBytes) throw new InstallError("download", `${url} is larger than the pinned ${maxBytes} bytes, so the download was stopped`);
      chunks.push(chunk);
    }
  } catch (error) {
    if (error instanceof InstallError) throw error;
    throw new InstallError("download", `the download of ${url} broke off: ${(error as Error).message}`);
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) {
    out.set(chunk, at);
    at += chunk.byteLength;
  }
  return out;
}

function unpack(archive: Uint8Array, platform: PlatformPin): Uint8Array {
  try {
    return readZipEntry(archive, platform.executable, MAX_EXECUTABLE_BYTES);
  } catch (error) {
    throw new InstallError("archive", `the verified archive ${platform.archive} could not be unpacked: ${(error as Error).message}`);
  }
}

export async function installGltfpack(options: InstallOptions): Promise<Installed> {
  const pin = options.pin ?? GLTFPACK_RELEASE;
  const key = options.key ?? platformKey();
  const platform = platformPin(pin, key);
  const present = lookupInstalled(options.root, pin, key);
  if (present.state === "ready") return { path: present.path, status: "already installed", version: pin.version, sha256: platform.executableSha256 };
  const url = `${pin.baseUrl}${platform.archive}`;
  const archive = await (options.download ?? fetchWithLimit)(url, platform.archiveBytes);
  const actual = sha256Of(archive);
  if (actual !== platform.archiveSha256) {
    throw new InstallError("hash", `${url} has sha256 ${actual}, but ${platform.archiveSha256} is pinned; the download was refused and discarded, and nothing was installed`);
  }
  const executable = unpack(archive, platform);
  const unpacked = sha256Of(executable);
  if (unpacked !== platform.executableSha256) {
    throw new InstallError("hash", `${platform.executable} in ${platform.archive} has sha256 ${unpacked}, but ${platform.executableSha256} is pinned; nothing was installed`);
  }
  const target = installedPath(options.root, pin, key);
  const staging = `${target}.part`;
  try {
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(staging, executable);
    chmodSync(staging, 0o755);
    renameSync(staging, target);
  } catch (error) {
    rmSync(staging, { force: true });
    throw new InstallError("write", `could not write ${target}: ${(error as Error).message}`);
  }
  return { path: target, status: "installed", version: pin.version, sha256: unpacked };
}
