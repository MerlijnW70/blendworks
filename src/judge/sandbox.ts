import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const BLENDER_FLAGS = ["--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1"] as const;
const OUTPUT_TAIL = 16_384;

export type Limits = { timeoutMs: number; memoryBytes: number };

export type Isolation = { network: "isolated" | "not isolated"; memory: string; timeoutMs: number; platform: string };

export type Plan = { command: string; args: string[]; isolation: Isolation };

export type Tools = { platform: NodeJS.Platform; unshare: boolean; prlimit: boolean };

export type RunResult = { code: number | null; signal: NodeJS.Signals | null; timedOut: boolean; output: string };

function works(command: string, args: string[]): boolean {
  const result = spawnSync(command, args, { stdio: "ignore", timeout: 10_000 });
  return result.status === 0;
}

let detected: Tools | undefined;

export function detectTools(): Tools {
  if (detected) return detected;
  const platform = process.platform;
  const linux = platform === "linux";
  detected = { platform, unshare: linux && works("unshare", ["-rn", "true"]), prlimit: linux && works("prlimit", ["--version"]) };
  return detected;
}

export function planSandbox(blender: string, script: string, scriptArgs: string[], limits: Limits, tools: Tools): Plan {
  const blenderArgs = [...BLENDER_FLAGS, "--python", script, "--", ...scriptArgs];
  const memoryMb = Math.floor(limits.memoryBytes / (1024 * 1024));
  const withCap = [...blenderArgs, "--memory-mb", String(memoryMb)];
  if (tools.platform === "win32") {
    return {
      command: blender,
      args: withCap,
      isolation: { network: "not isolated", memory: `job object, ${memoryMb} MB, no child processes`, timeoutMs: limits.timeoutMs, platform: "windows" },
    };
  }
  const prefix: string[] = [];
  if (tools.prlimit) prefix.push("prlimit", `--as=${limits.memoryBytes}`, "--core=0", "--");
  prefix.push(blender, ...withCap);
  const network = tools.unshare ? "isolated" : "not isolated";
  const memory = tools.prlimit ? `prlimit address space, ${memoryMb} MB` : `setrlimit address space, ${memoryMb} MB`;
  const isolation: Isolation = { network, memory, timeoutMs: limits.timeoutMs, platform: tools.platform };
  if (tools.unshare) return { command: "unshare", args: ["-rn", ...prefix], isolation };
  const [command, ...args] = prefix;
  return { command: command ?? blender, args, isolation };
}

export function sandboxEnvironment(home: string): NodeJS.ProcessEnv {
  const keep = ["PATH", "Path", "SystemRoot", "SYSTEMROOT", "windir", "LANG"];
  const environment: NodeJS.ProcessEnv = {};
  for (const name of keep) if (process.env[name] !== undefined) environment[name] = process.env[name];
  for (const name of ["BLENDER_USER_RESOURCES", "BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES", "BLENDER_USER_EXTENSIONS"]) {
    const folder = join(home, name.toLowerCase());
    mkdirSync(folder, { recursive: true });
    environment[name] = folder;
  }
  Object.assign(environment, { HOME: home, USERPROFILE: home, TEMP: home, TMP: home, TMPDIR: home });
  Object.assign(environment, { CUDA_VISIBLE_DEVICES: "", HIP_VISIBLE_DEVICES: "" });
  return environment;
}

export async function runSandboxed(plan: Plan, workDir: string): Promise<RunResult> {
  const home = mkdtempSync(join(tmpdir(), "blendworks-sandbox-"));
  try {
    return await new Promise<RunResult>((resolve, reject) => {
      const child = spawn(plan.command, plan.args, {
        cwd: workDir,
        env: sandboxEnvironment(home),
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });
      let output = "";
      let timedOut = false;
      const keep = (chunk: Buffer) => {
        output = (output + chunk.toString("utf8")).slice(-OUTPUT_TAIL);
      };
      child.stdout.on("data", keep);
      child.stderr.on("data", keep);
      const timer = setTimeout(() => {
        timedOut = true;
        child.kill("SIGKILL");
      }, plan.isolation.timeoutMs);
      child.on("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.on("close", (code, signal) => {
        clearTimeout(timer);
        resolve({ code, signal, timedOut, output });
      });
    });
  } finally {
    rmSync(home, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
