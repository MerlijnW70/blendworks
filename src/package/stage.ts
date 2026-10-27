import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { planSandbox, runSandboxed, type SandboxDevice } from "../judge/sandbox.js";
import { SCRIPTS_DIR, seconds, StageFailure, workOut, type Sandbox, type StageResult } from "../judge/stages.js";

export const PACKAGE_SCRIPTS = fileURLToPath(new URL("../../bridge/package/", import.meta.url));

const LOW_INTEGRITY_LAUNCH_FAILED = 120;

function readOutput(path: string): unknown {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return undefined;
  }
}

export async function runPackageScript(script: string, scriptArgs: string[], outputPath: string, sandbox: Sandbox, device: SandboxDevice = "cpu"): Promise<StageResult> {
  const { blender, limits, tools, workDir } = sandbox;
  const view = { workDir, writable: [workOut(sandbox)], readOnly: [SCRIPTS_DIR, PACKAGE_SCRIPTS, sandbox.delivery] };
  const plan = planSandbox(blender, join(PACKAGE_SCRIPTS, script), scriptArgs, limits, tools, device, view);
  const started = performance.now();
  const result = await runSandboxed(plan, workDir);
  const elapsed = seconds(performance.now() - started);
  if (result.timedOut) throw new StageFailure({ stage: "package", code: "timeout", message: `Blender took longer than ${limits.timeoutMs / 1000} s and was stopped` });
  const output = readOutput(outputPath);
  if (output === undefined && result.code === LOW_INTEGRITY_LAUNCH_FAILED && plan.lowIntegrity) {
    throw new StageFailure({ stage: "package", code: "sandbox", message: `the low-integrity launcher could not start Blender: ${result.output.trim().slice(-300)}` });
  }
  if (output === undefined) {
    const tail = result.output.trim().split("\n").slice(-3).join(" | ").slice(0, 400);
    throw new StageFailure({
      stage: "package",
      code: "crashed",
      message: `Blender exited with code ${result.code ?? result.signal} without a result (out of memory under the ${limits.memoryBytes / 1048576} MB cap, or a crash): ${tail}`,
    });
  }
  return { output, isolation: plan.isolation, seconds: elapsed };
}
