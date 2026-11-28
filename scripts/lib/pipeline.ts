import { spawn, spawnSync } from "node:child_process";
import { fileLimitMs, heartbeatMs } from "./file-limits.js";
import { repoRoot } from "./paths.js";
import { type FileEvent, LineSplitter, overdueReason, parseFileEvent, Progress, PROGRESS_VARIABLE, WaitLog } from "./progress.js";
import { STAGE_VARIABLE, TIMINGS_VARIABLE } from "./timings.js";

export type Step = { name: string; command: string; args: string[]; env?: NodeJS.ProcessEnv };

export type StepResult = { name: string; passed: boolean; seconds: number; output: string; cancelled?: boolean };

export type StepHooks = { onFile?: (event: FileEvent) => void; onReady?: (stop: (reason: string) => void) => void };

export type PhaseOptions = { keepGoing?: boolean; onFile?: (step: string, event: FileEvent) => void; heartbeatMs?: number; checkMs?: number; waitLog?: string; limitMs?: number; exempt?: Record<string, string>; print?: (line: string) => void; now?: () => number };

const TAIL_LINES = 4;
const FAILURE_LINES = 200;
const WATCH_MS = 5_000;

export const VITEST_REPORTERS = ["--reporter=default", "--reporter=./test/setup/progress-reporter.ts"];

export function npmStep(script: string, args: string[] = [], extra: NodeJS.ProcessEnv = {}, hidden: string[] = []): Step {
  const cli = process.env["npm_execpath"];
  const label = args.length > 2 ? `${script} (${args.length} files)` : [script, ...args].join(" ");
  const env = { [STAGE_VARIABLE]: script, ...extra };
  const all = [...args, ...hidden];
  const scriptArgs = ["run", "--silent", script, ...(all.length > 0 ? ["--", ...all] : [])];
  if (cli !== undefined && cli !== "") return { name: label, command: process.execPath, args: [cli, ...scriptArgs], env };
  return { name: label, command: "npm", args: scriptArgs, env };
}

function killTree(pid: number | undefined): void {
  if (pid === undefined) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
    return;
  }
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
    return;
  }
}

export function runStep(step: Step, signal?: AbortSignal, hooks: StepHooks = {}): Promise<StepResult> {
  return new Promise((resolve) => {
    const started = performance.now();
    const chunks: Buffer[] = [];
    const child = spawn(step.command, step.args, {
      cwd: repoRoot,
      env: { ...process.env, ...step.env },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      detached: process.platform !== "win32",
      shell: step.command === "npm" && process.platform === "win32",
    });
    const lines = new LineSplitter();
    child.stdout.on("data", (chunk: Buffer) => {
      for (const line of lines.push(chunk.toString("utf8"))) {
        const event = parseFileEvent(line);
        if (event === undefined) chunks.push(Buffer.from(`${line}\n`));
        else hooks.onFile?.(event);
      }
    });
    child.stderr.on("data", (chunk: Buffer) => chunks.push(chunk));
    let cancelled = false;
    let stopReason: string | undefined;
    const finish = (passed: boolean, extra = ""): void => {
      const rest = lines.rest();
      if (rest !== "") chunks.push(Buffer.from(rest));
      const stopped = stopReason === undefined ? "" : `\n${stopReason}\n`;
      resolve({ name: step.name, passed: passed && !cancelled && stopReason === undefined, seconds: (performance.now() - started) / 1000, output: Buffer.concat(chunks).toString("utf8") + stopped + extra, ...(cancelled ? { cancelled } : {}) });
    };
    hooks.onReady?.((reason) => {
      stopReason ??= reason;
      killTree(child.pid);
    });
    const cancel = (): void => {
      cancelled = true;
      killTree(child.pid);
    };
    if (signal?.aborted === true) cancel();
    else signal?.addEventListener("abort", cancel, { once: true });
    child.on("error", (error) => finish(false, `\n${error.message}\n`));
    child.on("close", (code) => finish(code === 0));
  });
}

export function report(result: StepResult): void {
  const lines = result.output.replace(/\u001b\[[0-9;]*[A-Za-z]/g, "").split(/\r?\n/).filter((line) => line.trim() !== "");
  console.log(`${result.cancelled === true ? "stop" : result.passed ? "ok  " : "FAIL"} ${result.name} (${result.seconds.toFixed(1)} s)`);
  const shown = result.cancelled === true ? [] : result.passed ? lines.slice(-TAIL_LINES) : lines.slice(-FAILURE_LINES);
  for (const line of shown) console.log(`     ${line}`);
}

export async function runPhases(phases: Step[][], options: PhaseOptions = {}): Promise<{ passed: boolean; results: StepResult[]; seconds: number }> {
  const started = performance.now();
  const limitMs = options.limitMs ?? fileLimitMs();
  const beatMs = options.heartbeatMs ?? heartbeatMs();
  const progress = new Progress({ now: options.now ?? (() => performance.now()), print: options.print ?? ((line) => console.log(line)), limitMs, ...(options.exempt === undefined ? {} : { exempt: options.exempt }) });
  const stops = new Map<string, (reason: string) => void>();
  const beat = setInterval(() => progress.heartbeat(), beatMs);
  const waits = new WaitLog(options.waitLog ?? process.env[TIMINGS_VARIABLE]);
  const watch = setInterval(() => {
    for (const wait of waits.poll()) progress.waiting(wait);
    for (const late of progress.overdue()) stops.get(late.step)?.(overdueReason(late, limitMs));
  }, options.checkMs ?? Math.min(WATCH_MS, beatMs));
  beat.unref();
  watch.unref();
  const results: StepResult[] = [];
  let passed = true;
  try {
    for (const phase of phases) {
      const failFast = new AbortController();
      const phaseResults = await Promise.all(
        phase.map(async (step) => {
          progress.stepStarted(step.name);
          const result = await runStep({ ...step, env: { ...step.env, [PROGRESS_VARIABLE]: "1" } }, failFast.signal, {
            onFile: (event) => {
              progress.event(step.name, event);
              options.onFile?.(step.name, event);
            },
            onReady: (stop) => stops.set(step.name, stop),
          });
          stops.delete(step.name);
          progress.stepEnded(step.name);
          if (!result.passed && result.cancelled !== true && options.keepGoing !== true) failFast.abort();
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
  } finally {
    clearInterval(beat);
    clearInterval(watch);
  }
  const seconds = (performance.now() - started) / 1000;
  console.log(`${passed ? "passed" : "FAILED"} in ${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")} (${results.map((result) => `${result.name} ${result.seconds.toFixed(0)} s`).join(", ")})`);
  return { passed, results, seconds };
}
