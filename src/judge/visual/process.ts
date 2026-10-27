import { spawn } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { delimiter, join } from "node:path";

export const CLAUDE_VARIABLE = "BLENDWORKS_CLAUDE";
export const MAX_OUTPUT_BYTES = 32 * 1024 * 1024;

export type Run = { code: number | null; stdout: string; stderr: string; timedOut: boolean; missing: boolean };

export type SpawnOptions = { cwd: string; env: NodeJS.ProcessEnv; timeoutMs: number; stdin: string };

export type Spawner = (command: string, args: string[], options: SpawnOptions) => Promise<Run>;

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

export function findClaude(env: NodeJS.ProcessEnv, platform: NodeJS.Platform = process.platform): string | null {
  const named = env[CLAUDE_VARIABLE]?.trim();
  if (named) return existsSync(named) ? named : null;
  const folders = (env.PATH ?? env.Path ?? "").split(delimiter).filter((folder) => folder !== "");
  for (const folder of folders) {
    if (platform !== "win32") {
      if (isFile(join(folder, "claude"))) return join(folder, "claude");
      continue;
    }
    if (isFile(join(folder, "claude.exe"))) return join(folder, "claude.exe");
    const bundled = join(folder, "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe");
    if (isFile(join(folder, "claude.cmd")) && isFile(bundled)) return bundled;
  }
  return null;
}

export const runProcess: Spawner = (command, args, options) =>
  new Promise((resolve) => {
    const child = spawn(command, args, { cwd: options.cwd, env: options.env, stdio: ["pipe", "pipe", "pipe"], windowsHide: true, shell: false });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    let size = 0;
    let timedOut = false;
    let settled = false;
    const finish = (run: Run) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(run);
    };
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, options.timeoutMs);
    const collect = (into: Buffer[]) => (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_OUTPUT_BYTES) child.kill("SIGKILL");
      else into.push(chunk);
    };
    child.stdout.on("data", collect(out));
    child.stderr.on("data", collect(err));
    child.stdin.on("error", () => undefined);
    child.on("error", (error: NodeJS.ErrnoException) => finish({ code: null, stdout: "", stderr: error.message, timedOut: false, missing: error.code === "ENOENT" }));
    child.on("close", (code) => finish({ code, stdout: Buffer.concat(out).toString("utf8"), stderr: Buffer.concat(err).toString("utf8"), timedOut, missing: false }));
    child.stdin.end(options.stdin);
  });
