import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, lstatSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { cacheRoot } from "../package/native-install.js";

export const KERNEL_CACHE = "gpu-kernels";
export const KERNELS = "kernels";
export const READY = "ready";
export const UNAVAILABLE = "unavailable";
export const MANIFEST = "kernels.json";

export type KernelManifest = Record<string, string>;

const LOW_LABEL = /Low Mandatory Level/i;

export function kernelCache(root: string = cacheRoot()): string {
  return join(root, KERNEL_CACHE);
}

export function kernelVariables(folder: string): Record<string, string> {
  return { OPTIX_CACHE_PATH: join(folder, "optix"), CUDA_CACHE_PATH: join(folder, "cuda") };
}

function files(folder: string, under: string = folder): string[] | null {
  const found: string[] = [];
  for (const entry of readdirSync(under, { withFileTypes: true })) {
    const path = join(under, entry.name);
    if (entry.isDirectory()) {
      const nested = files(folder, path);
      if (nested === null) return null;
      found.push(...nested);
    } else if (entry.isFile() && !lstatSync(path).isSymbolicLink()) found.push(relative(folder, path).split(sep).join("/"));
    else return null;
  }
  return found.sort();
}

export function hashKernels(folder: string): KernelManifest | null {
  if (!existsSync(folder)) return {};
  const listed = files(folder);
  if (listed === null) return null;
  return Object.fromEntries(listed.map((name) => [name, createHash("sha256").update(readFileSync(join(folder, ...name.split("/")))).digest("hex")]));
}

function same(first: KernelManifest | null, second: KernelManifest | null): boolean {
  if (first === null || second === null) return false;
  const names = Object.keys(first);
  return names.length === Object.keys(second).length && names.every((name) => first[name] === second[name]);
}

export function readManifest(trusted: string): KernelManifest | null {
  try {
    const value: unknown = JSON.parse(readFileSync(join(trusted, MANIFEST), "utf8"));
    if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.every(([, hash]) => typeof hash === "string" && /^[0-9a-f]{64}$/.test(hash)) ? (Object.fromEntries(entries) as KernelManifest) : null;
  } catch {
    return null;
  }
}

export function kernelsIntact(trusted: string): boolean {
  return existsSync(join(trusted, READY)) && same(readManifest(trusted), hashKernels(join(trusted, KERNELS)));
}

function windowsSeal(folder: string): boolean {
  const options = { encoding: "utf8" as const, windowsHide: true, timeout: 60_000 };
  const set = spawnSync("icacls", [folder, "/setintegritylevel", "(OI)(CI)M", "/T", "/C", "/Q"], options);
  if (set.status !== 0) return false;
  const shown = spawnSync("icacls", [folder, "/T", "/C"], options);
  return shown.status === 0 && !LOW_LABEL.test(shown.stdout);
}

export function sealKernels(trusted: string, platform: NodeJS.Platform = process.platform): boolean {
  const manifest = hashKernels(join(trusted, KERNELS));
  if (manifest === null) return false;
  if (platform === "win32" && !windowsSeal(trusted)) return false;
  writeFileSync(join(trusted, MANIFEST), `${JSON.stringify(manifest, null, 2)}\n`);
  return true;
}

export function discardKernels(trusted: string): void {
  rmSync(trusted, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}

export function privateKernels(home: string, root: string = cacheRoot()): Record<string, string> {
  const own = join(home, KERNEL_CACHE);
  mkdirSync(own, { recursive: true });
  const trusted = kernelCache(root);
  if (!existsSync(join(trusted, READY))) return kernelVariables(own);
  const manifest = readManifest(trusted);
  if (!same(manifest, hashKernels(join(trusted, KERNELS)))) {
    discardKernels(trusted);
    return kernelVariables(own);
  }
  cpSync(join(trusted, KERNELS), own, { recursive: true });
  if (!same(manifest, hashKernels(own))) {
    rmSync(own, { recursive: true, force: true });
    mkdirSync(own, { recursive: true });
    discardKernels(trusted);
  }
  return kernelVariables(own);
}
