import { existsSync, mkdirSync, mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { cacheRoot } from "../package/native-install.js";
import { KERNEL_CACHE, KERNELS, kernelCache, READY, UNAVAILABLE } from "./kernel-cache.js";
import { planSandbox, runSandboxed } from "./sandbox.js";
import { SCRIPTS_DIR, type Sandbox } from "./stages.js";

function warmed(output: string): boolean {
  try {
    return (JSON.parse(readFileSync(join(output, "warm.json"), "utf8")) as { ok?: unknown }).ok === true;
  } catch {
    return false;
  }
}

export async function warmKernels(sandbox: Sandbox, backends: readonly string[], root: string = cacheRoot()): Promise<void> {
  const trusted = kernelCache(root);
  if (existsSync(join(trusted, READY)) || existsSync(join(trusted, UNAVAILABLE))) return;
  mkdirSync(root, { recursive: true });
  const staging = mkdtempSync(join(root, `${KERNEL_CACHE}-`));
  try {
    const output = join(staging, "out");
    const kernels = join(staging, KERNELS);
    const view = { workDir: staging, writable: [output, kernels], readOnly: [SCRIPTS_DIR] };
    const plan = planSandbox(sandbox.blender, join(SCRIPTS_DIR, "gpu_warm.py"), [output, "--device", "AUTO", "--backends", backends.join(",")], sandbox.limits, sandbox.tools, "gpu", view);
    const result = await runSandboxed({ ...plan, kernels }, staging);
    const ok = !result.timedOut && warmed(output);
    rmSync(output, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    writeFileSync(join(staging, ok ? READY : UNAVAILABLE), "");
    renameSync(staging, trusted);
  } catch (error) {
    if (!existsSync(trusted)) throw error;
  } finally {
    rmSync(staging, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
