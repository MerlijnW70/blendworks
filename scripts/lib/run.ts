import { spawn } from "node:child_process";
import { blenderJobs, blenderThreadArguments } from "../../src/blender.js";
import { type SlotOptions, withSlot } from "./slots.js";

export type RunOptions = Omit<SlotOptions, "timeoutMs"> & { cwd?: string; env?: NodeJS.ProcessEnv; timeoutMs?: number; waitTimeoutMs?: number; onStart?: () => void };

export type RunResult = { code: number | null; signal: NodeJS.Signals | null; stdout: string; stderr: string; seconds: number; waitedSeconds: number; timedOut: boolean };

function run(command: string, args: string[], options: RunOptions): Promise<Omit<RunResult, "waitedSeconds">> {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const child = spawn(command, args, { cwd: options.cwd, env: options.env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    let timedOut = false;
    const timer =
      options.timeoutMs === undefined
        ? undefined
        : setTimeout(() => {
            timedOut = true;
            child.kill("SIGKILL");
          }, options.timeoutMs);
    child.stdout.on("data", (chunk: Buffer) => out.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => err.push(chunk));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code, signal) => {
      clearTimeout(timer);
      resolve({ code, signal, stdout: Buffer.concat(out).toString("utf8"), stderr: Buffer.concat(err).toString("utf8"), seconds: (performance.now() - started) / 1000, timedOut });
    });
  });
}

export function runUnderSlot(command: string, args: string[], options: RunOptions = {}): Promise<RunResult> {
  const { root, jobs, pollMs, label, waitTimeoutMs } = options;
  const slotOptions = { ...(root === undefined ? {} : { root }), ...(jobs === undefined ? {} : { jobs }), ...(pollMs === undefined ? {} : { pollMs }), ...(label === undefined ? {} : { label }), ...(waitTimeoutMs === undefined ? {} : { timeoutMs: waitTimeoutMs }) };
  return withSlot(async (slot) => {
    options.onStart?.();
    return { ...(await run(command, args, options)), waitedSeconds: slot.waitedMs / 1000 };
  }, slotOptions);
}

export function runBlender(blender: string, args: string[], options: RunOptions = {}): Promise<RunResult> {
  const jobs = options.jobs ?? blenderJobs();
  return runUnderSlot(blender, [...blenderThreadArguments(jobs), ...args], { ...options, jobs });
}
