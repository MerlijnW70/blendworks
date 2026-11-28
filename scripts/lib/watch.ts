import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { constants, setPriority } from "node:os";
import { join, resolve } from "node:path";
import { blenderJobs, JOBS_VARIABLE } from "../../src/blender.js";
import { cacheRoot, CACHE_VARIABLE, repoRoot } from "./paths.js";
import { activeSlots } from "./slots.js";

export type WatchOptions = { repo: string; branch: string; out: string; intervalMs: number; once: boolean; command: string[]; idleSlots: string | undefined };

export type WatchResult = { commit: string; subject: string; passed: boolean; seconds: number; failing: string[]; tail: string[]; log: string; finishedAt: string };

const TAIL = 12;
const FAILED_FILE = /^(?:FAIL|stop)\s+\[[^\]]+\]\s+(\S+)/;
const FAILED_BRIDGE = /^FAIL\s+(test_\S+\.py)\b/;

export function parseWatchArgs(argv: string[], cwd: string = process.cwd()): WatchOptions | string {
  const out: WatchOptions = { repo: repoRoot, branch: "main", out: join(cacheRoot(), "watch"), intervalMs: 60_000, once: false, command: ["npm", "run", "check"], idleSlots: join(cacheRoot(), "slots") };
  for (let at = 0; at < argv.length; at += 1) {
    const argument = argv[at] as string;
    const value = argv[at + 1];
    const needs = (): string | undefined => (value === undefined || value.startsWith("--") ? `${argument} needs a value` : undefined);
    if (argument === "--once") out.once = true;
    else if (["--repo", "--branch", "--out", "--interval"].includes(argument)) {
      const problem = needs();
      if (problem !== undefined) return problem;
      at += 1;
      if (argument === "--repo") out.repo = resolve(cwd, value as string);
      if (argument === "--branch") out.branch = value as string;
      if (argument === "--out") out.out = resolve(cwd, value as string);
      if (argument === "--interval") {
        if (!/^\d+$/.test(value as string) || Number(value) < 1) return "--interval needs whole seconds of at least 1";
        out.intervalMs = Number(value) * 1000;
      }
    } else return `unknown argument ${argument}; usage: npm run check:watch -- [--repo <path>] [--branch main] [--out <dir>] [--interval <seconds>] [--once]`;
  }
  if (out.repo !== repoRoot) out.idleSlots = join(out.repo, ".cache", "slots");
  return out;
}

function git(cwd: string, args: string[]): string {
  return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

export function failingFiles(log: string): string[] {
  const found = new Set<string>();
  for (const line of log.split(/\r?\n/)) {
    const match = FAILED_FILE.exec(line.trim()) ?? FAILED_BRIDGE.exec(line.trim());
    if (match !== null) found.add(match[1] as string);
  }
  return [...found];
}

export function statusLine(result: WatchResult): string {
  const time = `${Math.floor(result.seconds / 60)}:${String(Math.round(result.seconds % 60)).padStart(2, "0")}`;
  if (result.passed) return `${result.finishedAt} ${result.commit.slice(0, 12)} pass ${time} ${result.subject}`;
  const files = result.failing.length > 0 ? result.failing.join(", ") : "no failing file named";
  return `${result.finishedAt} ${result.commit.slice(0, 12)} FAIL ${time} ${files}: ${result.tail.slice(-3).join(" | ")}`;
}

function prepare(options: WatchOptions, commit: string): string {
  const work = join(options.out, "work");
  if (!existsSync(join(work, ".git"))) git(options.out, ["clone", "--quiet", "--no-checkout", options.repo, work]);
  git(work, ["fetch", "--quiet", "--force", options.repo, `+refs/heads/${options.branch}:refs/watch/${options.branch}`]);
  git(work, ["checkout", "--quiet", "--force", "--detach", commit]);
  git(work, ["clean", "-fdxq", "-e", "node_modules", "-e", ".cache"]);
  const lock = join(work, "package-lock.json");
  if (existsSync(lock)) {
    const digest = createHash("sha256").update(readFileSync(lock)).digest("hex");
    const stamp = join(options.out, "installed-lock.sha256");
    if (!existsSync(stamp) || readFileSync(stamp, "utf8") !== digest || !existsSync(join(work, "node_modules"))) {
      execFileSync("npm", ["ci", "--no-audit", "--no-fund"], { cwd: work, stdio: "ignore", shell: process.platform === "win32" });
      writeFileSync(stamp, digest);
    }
  }
  return work;
}

function runCheck(options: WatchOptions, work: string, logPath: string): Promise<{ code: number | null; seconds: number }> {
  return new Promise((done) => {
    const started = performance.now();
    const log = createWriteStream(logPath);
    const env = { ...process.env, [CACHE_VARIABLE]: join(work, ".cache"), [JOBS_VARIABLE]: process.env[JOBS_VARIABLE] ?? String(blenderJobs()) };
    const [command, ...args] = options.command as [string, ...string[]];
    const child = spawn(command, args, { cwd: work, env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true, shell: process.platform === "win32" && command === "npm" });
    child.stdout.pipe(log, { end: false });
    child.stderr.pipe(log, { end: false });
    child.on("close", (code) => log.end(() => done({ code, seconds: (performance.now() - started) / 1000 })));
    child.on("error", (error) => log.end(`\n${error.message}\n`, () => done({ code: null, seconds: (performance.now() - started) / 1000 })));
  });
}

async function waitForIdleSlots(options: WatchOptions, sleep: (ms: number) => Promise<void>): Promise<void> {
  const slots = options.idleSlots;
  if (slots === undefined || !existsSync(slots)) return;
  while (activeSlots(join(slots, "..")).length > 0) await sleep(Math.min(options.intervalMs, 30_000));
}

export async function checkCommit(options: WatchOptions, commit: string, sleep: (ms: number) => Promise<void>): Promise<WatchResult> {
  const results = join(options.out, "results");
  const logs = join(options.out, "logs");
  mkdirSync(results, { recursive: true });
  mkdirSync(logs, { recursive: true });
  await waitForIdleSlots(options, sleep);
  const work = prepare(options, commit);
  const logPath = join(logs, `${commit}.log`);
  const run = await runCheck(options, work, logPath);
  const text = readFileSync(logPath, "utf8");
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");
  const result: WatchResult = { commit, subject: git(work, ["log", "-1", "--format=%s", commit]), passed: run.code === 0, seconds: run.seconds, failing: run.code === 0 ? [] : failingFiles(text), tail: lines.slice(-TAIL), log: logPath, finishedAt: new Date().toISOString() };
  writeFileSync(join(results, `${commit}.json`), `${JSON.stringify(result, null, 2)}\n`);
  appendFileSync(join(options.out, "status.log"), `${statusLine(result)}\n`);
  return result;
}

export function lowerOwnPriority(): void {
  try {
    setPriority(constants.priority.PRIORITY_LOW);
  } catch {
    return;
  }
}

export async function watch(options: WatchOptions, sleep: (ms: number) => Promise<void> = (ms) => new Promise((done) => setTimeout(done, ms)), print: (line: string) => void = (line) => console.log(line)): Promise<WatchResult[]> {
  mkdirSync(options.out, { recursive: true });
  const done: WatchResult[] = [];
  for (;;) {
    const commit = git(options.repo, ["rev-parse", "--verify", `refs/heads/${options.branch}^{commit}`]);
    if (!existsSync(join(options.out, "results", `${commit}.json`))) {
      print(`checking ${options.branch} at ${commit.slice(0, 12)} in ${join(options.out, "work")}`);
      const result = await checkCommit(options, commit, sleep);
      done.push(result);
      print(statusLine(result));
    }
    if (options.once) return done;
    await sleep(options.intervalMs);
  }
}
