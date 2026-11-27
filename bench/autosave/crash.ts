import { spawn } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";

const USAGE = "npx tsx bench/autosave/crash.ts <bridge folder> <work folder> <check|full> <threads> [command ...]";
const [bridge, work, size, threads, ...rest] = process.argv.slice(2);
if (bridge === undefined || work === undefined || size === undefined || threads === undefined) throw new Error(USAGE);
const targets = rest.length > 0 ? rest : ["liquid_body", "tree_mesh", "ground_cover"];
const blender = process.env["BLENDER"] ?? "blender";
const KILL_AFTER_MS = 400;

type Run = { done?: string; killed?: { index: number; cmd: string }; recovered?: unknown };

function replies(folder: string): number {
  const path = join(folder, "replies.jsonl");
  return existsSync(path) ? readFileSync(path, "utf8").split("\n").filter((line) => line.trim() !== "").length : 0;
}

function runWorker(folder: string, target: string | undefined): Promise<Run> {
  const args = ["-b", "--factory-startup", "-t", threads!, "--python", resolve("bench/autosave/crash_worker.py"), "--", resolve(bridge!), folder, size!];
  const child = spawn(blender, args, { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
  const run: Run = {};
  child.stderr.resume();
  createInterface({ input: child.stdout }).on("line", (line) => {
    if (line.startsWith("DONE ")) run.done = line.slice(5);
    if (line.startsWith("RECOVERED ")) run.recovered = JSON.parse(line.slice(10));
    const call = /^CALL (\d+) (\S+)$/.exec(line);
    if (call && target !== undefined && call[2] === target && run.killed === undefined) {
      run.killed = { index: Number(call[1]), cmd: target };
      setTimeout(() => child.pid !== undefined && process.kill(child.pid, "SIGKILL"), KILL_AFTER_MS);
    }
  });
  return new Promise((resolveRun) => child.once("exit", (code) => resolveRun({ ...run, ...(run.done === undefined && run.killed === undefined ? { recovered: { exit: code } } : {}) })));
}

const straightFolder = resolve(work, "straight");
const crashedFolder = resolve(work, "crashed");
for (const folder of [straightFolder, crashedFolder]) rmSync(folder, { recursive: true, force: true });
const straight = await runWorker(straightFolder, undefined);
const log: unknown[] = [];
for (const target of targets) {
  const run = await runWorker(crashedFolder, target);
  if (run.killed === undefined) throw new Error(`${target} never ran`);
  const finished = replies(crashedFolder) > run.killed.index;
  log.push({ killed: run.killed, recovered_before: run.recovered ?? null, finished_before_kill: finished });
}
const last = await runWorker(crashedFolder, undefined);
log.push({ recovered_before: last.recovered });
console.log(JSON.stringify({ size, threads, straight: straight.done, crashed: last.done, equal: straight.done !== undefined && straight.done === last.done, runs: log }, null, 1));
