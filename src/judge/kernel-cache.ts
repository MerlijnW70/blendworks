import { cpSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { cacheRoot } from "../package/native-install.js";

export const KERNEL_CACHE = "gpu-kernels";
export const KERNELS = "kernels";
export const READY = "ready";
export const UNAVAILABLE = "unavailable";

export function kernelCache(root: string = cacheRoot()): string {
  return join(root, KERNEL_CACHE);
}

export function kernelVariables(folder: string): Record<string, string> {
  return { OPTIX_CACHE_PATH: join(folder, "optix"), CUDA_CACHE_PATH: join(folder, "cuda") };
}

export function privateKernels(home: string, root: string = cacheRoot()): Record<string, string> {
  const own = join(home, KERNEL_CACHE);
  mkdirSync(own, { recursive: true });
  const trusted = kernelCache(root);
  if (existsSync(join(trusted, READY))) cpSync(join(trusted, KERNELS), own, { recursive: true });
  return kernelVariables(own);
}
