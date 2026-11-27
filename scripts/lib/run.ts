import { spawn } from "node:child_process";
import { blenderJobs, blenderThreadArguments } from "../../src/blender.js";
import { type Slot, type SlotOptions, withSlot } from "./slots.js";

export type RunOptions = Omit<SlotOptions, "timeoutMs"> & { cwd?: string; env?: NodeJS.ProcessEnv; timeoutMs?: number; waitTimeoutMs?: number; onStart?: () => void; onSpawn?: (pid: number, slot?: Pick<Slot, "attach">) => void; onStdout?: (chunk: Buffer) => void; signal?: AbortSignal };

export type RunResult = { code: number | null; signal: NodeJS.Signals | null; stdout: string; stderr: string; seconds: number; waitedSeconds: number; timedOut: boolean };

function run(command: string, args: string[], options: RunOptions): Promise<Omit<RunResult, "waitedSeconds">> {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const child = spawn(command, args, { cwd: options.cwd, env: options.env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    if (child.pid !== undefined) options.onSpawn?.(child.pid);
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    let timedOut = false;
    const stop = (): void => {
      timedOut = true;
      child.kill("SIGKILL");
    };
    const timer = options.timeoutMs === undefined ? undefined : setTimeout(stop, options.timeoutMs);
    if (options.signal?.aborted === true) stop();
    else options.signal?.addEventListener("abort", stop, { once: true });
    child.stdout.on("data", (chunk: Buffer) => {
      out.push(chunk);
      options.onStdout?.(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => err.push(chunk));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code, signal) => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", stop);
      resolve({ code, signal, stdout: Buffer.concat(out).toString("utf8"), stderr: Buffer.concat(err).toString("utf8"), seconds: (performance.now() - started) / 1000, timedOut });
    });
  });
}

export function runUnderSlot(command: string, args: string[], options: RunOptions = {}): Promise<RunResult> {
  const { root, jobs, pollMs, label, waitTimeoutMs, file, needMb, budgetMb } = options;
  const slotOptions = {
    ...(root === undefined ? {} : { root }),
    ...(jobs === undefined ? {} : { jobs }),
    ...(pollMs === undefined ? {} : { pollMs }),
    ...(label === undefined ? {} : { label }),
    ...(waitTimeoutMs === undefined ? {} : { timeoutMs: waitTimeoutMs }),
    ...(file === undefined ? {} : { file }),
    ...(needMb === undefined ? {} : { needMb }),
    ...(budgetMb === undefined ? {} : { budgetMb }),
  };
  return withSlot(async (slot) => {
    options.onStart?.();
    const onSpawn = (pid: number): void => {
      slot.attach(pid);
      options.onSpawn?.(pid, slot);
    };
    return { ...(await run(command, args, { ...options, onSpawn })), waitedSeconds: slot.waitedMs / 1000 };
  }, slotOptions);
}

export function runBlender(blender: string, args: string[], options: RunOptions = {}): Promise<RunResult> {
  const jobs = options.jobs ?? blenderJobs();
  return runUnderSlot(blender, [...blenderThreadArguments(jobs), ...args], { ...options, jobs });
}
