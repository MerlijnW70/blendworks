import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const CACHE_VARIABLE = "BLENDWORKS_CACHE";
export const CACHE_MARKER = ".blendworks-cache";

export function cacheRoot(env: NodeJS.ProcessEnv = process.env): string {
  const requested = env[CACHE_VARIABLE];
  return requested === undefined || requested === "" ? join(repoRoot, ".cache") : resolve(requested);
}

export function ensureCacheRoot(root: string = cacheRoot()): string {
  mkdirSync(root, { recursive: true });
  const marker = join(root, CACHE_MARKER);
  if (!existsSync(marker)) writeFileSync(marker, "Blendworks cache; npm run clean removes this folder.\n");
  return root;
}
