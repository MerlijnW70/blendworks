import { spawn } from "node:child_process";
import { repoRoot } from "./paths.js";
import { STAGE_VARIABLE } from "./timings.js";

export type Step = { name: string; command: string; args: string[]; env?: NodeJS.ProcessEnv };

export type StepResult = { name: string; passed: boolean; seconds: number; output: string };

const TAIL_LINES = 4;
const FAILURE_LINES = 200;

export function npmStep(script: string, args: string[] = [], extra: NodeJS.ProcessEnv = {}): Step {
  const cli = process.env["npm_execpath"];
  const label = args.length > 2 ? `${script} (${args.length} files)` : [script, ...args].join(" ");
  const env = { [STAGE_VARIABLE]: script, ...extra };
  const scriptArgs = ["run", "--silent", script, ...(args.length > 0 ? ["--", ...args] : [])];
  if (cli !== undefined && cli !== "") return { name: label, command: process.execPath, args: [cli, ...scriptArgs], env };
  return { name: label, command: "npm", args: scriptArgs, env };
}

export function runStep(step: Step): Promise<StepResult> {
  return new Promise((resolve) => {
    const started = performance.now();
    const chunks: Buffer[] = [];
    const child = spawn(step.command, step.args, {
      cwd: repoRoot,
      env: { ...process.env, ...step.env },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      shell: step.command === "npm" && process.platform === "win32",
    });
    child.stdout.on("data", (chunk: Buffer) => chunks.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => chunks.push(chunk));
    const finish = (passed: boolean, extra = ""): void => resolve({ name: step.name, passed, seconds: (performance.now() - started) / 1000, output: Buffer.concat(chunks).toString("utf8") + extra });
    child.on("error", (error) => finish(false, `\n${error.message}\n`));
    child.on("close", (code) => finish(code === 0));
  });
}

export function report(result: StepResult): void {
  const lines = result.output.replace(/\u001b\[[0-9;]*[A-Za-z]/g, "").split(/\r?\n/).filter((line) => line.trim() !== "");
  console.log(`${result.passed ? "ok  " : "FAIL"} ${result.name} (${result.seconds.toFixed(1)} s)`);
  const shown = result.passed ? lines.slice(-TAIL_LINES) : lines.slice(-FAILURE_LINES);
  for (const line of shown) console.log(`     ${line}`);
}

export async function runPhases(phases: Step[][]): Promise<{ passed: boolean; results: StepResult[]; seconds: number }> {
  const started = performance.now();
  const results: StepResult[] = [];
  let passed = true;
  for (const phase of phases) {
    const phaseResults = await Promise.all(
      phase.map(async (step) => {
        const result = await runStep(step);
        report(result);
        return result;
      }),
    );
    results.push(...phaseResults);
    if (phaseResults.some((result) => !result.passed)) {
      passed = false;
      break;
    }
  }
  const seconds = (performance.now() - started) / 1000;
  console.log(`${passed ? "passed" : "FAILED"} in ${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")} (${results.map((result) => `${result.name} ${result.seconds.toFixed(0)} s`).join(", ")})`);
  return { passed, results, seconds };
}
