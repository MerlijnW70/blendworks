import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { BLENDER_VERSION, blenderThreadArguments } from "../blender.js";

export const BLENDER_FLAGS = ["--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1"] as const;
const OUTPUT_TAIL = 16_384;
const JUDGE_SCRIPTS = fileURLToPath(new URL("../../bridge/judge/", import.meta.url));
export const MOUNT_SCRIPT = join(JUDGE_SCRIPTS, "sandbox.sh");
export const LOW_INTEGRITY_SCRIPT = join(JUDGE_SCRIPTS, "low_integrity.py");
export const NAMESPACE_FLAGS = ["--user", "--map-root-user", "--mount", "--pid", "--fork", "--kill-child", "--net"] as const;
export const SYSTEM_READ_ONLY = ["/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/etc", "/sys"] as const;
const GPU_DEVICES = ["/dev/dxg", "/dev/dri", "/dev/kfd", "/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools", "/dev/nvidia-modeset", "/dev/nvidia0", "/dev/nvidia1"];
const NEW_ROOT = ".sandbox-root";

export type Limits = { timeoutMs: number; memoryBytes: number };

export type Isolation = {
  network: "isolated" | "not isolated";
  memory: string;
  timeoutMs: number;
  platform: string;
  filesystem: string;
  processes: string;
};

export type View = { workDir: string; writable: string[]; readOnly: string[] };

export type Plan = { command: string; args: string[]; isolation: Isolation; gpu: boolean; writable: string[]; lowIntegrity: boolean };

export type SandboxDevice = "cpu" | "gpu";

export type Tools = { platform: NodeJS.Platform; unshare: boolean; prlimit: boolean; mountNamespace?: boolean; lowIntegrityPython?: string | null };

export type RunResult = { code: number | null; signal: NodeJS.Signals | null; timedOut: boolean; output: string };

function works(command: string, args: string[]): boolean {
  const result = spawnSync(command, args, { stdio: "ignore", timeout: 20_000 });
  return result.status === 0;
}

export function realPath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
}

function mountNamespaceWorks(): boolean {
  const root = mkdtempSync(join(tmpdir(), "blendworks-probe-"));
  try {
    mkdirSync(join(root, NEW_ROOT));
    return works("unshare", [...NAMESPACE_FLAGS, "sh", MOUNT_SCRIPT, join(root, NEW_ROOT), "--", ...SYSTEM_READ_ONLY, "--", "true"]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

export function blenderPython(blender: string): string | null {
  const candidate = join(dirname(realPath(blender)), BLENDER_VERSION, "python", "bin", "python.exe");
  return existsSync(candidate) ? candidate : null;
}

function lowIntegrityWorks(python: string): boolean {
  return works(python, ["-I", LOW_INTEGRITY_SCRIPT, "--", python, "-I", "-c", "pass"]);
}

let detected: Tools | undefined;

export function detectTools(blender?: string): Tools {
  if (detected && (detected.platform !== "win32" || blender === undefined || detected.lowIntegrityPython !== undefined)) return detected;
  const platform = process.platform;
  const linux = platform === "linux";
  const unshare = linux && works("unshare", ["-rn", "true"]);
  const tools: Tools = { platform, unshare, prlimit: linux && works("prlimit", ["--version"]), mountNamespace: unshare && mountNamespaceWorks() };
  if (platform === "win32" && blender !== undefined) {
    const python = blenderPython(blender);
    tools.lowIntegrityPython = python !== null && lowIntegrityWorks(python) ? python : null;
  }
  detected = tools;
  return tools;
}

function windowsPlan(blender: string, withCap: string[], limits: Limits, tools: Tools, gpu: boolean, view: View | undefined): Plan {
  const memoryMb = Math.floor(limits.memoryBytes / (1024 * 1024));
  const base = { network: "not isolated" as const, memory: `job object, ${memoryMb} MB, no child processes`, timeoutMs: limits.timeoutMs, platform: "windows", processes: "job object, no child processes" };
  const python = tools.lowIntegrityPython;
  if (python && view !== undefined) {
    return {
      command: python,
      args: ["-I", LOW_INTEGRITY_SCRIPT, "--", blender, ...withCap],
      isolation: { ...base, filesystem: "low integrity: writes only to the private work folder; reads are not limited" },
      gpu,
      writable: view.writable,
      lowIntegrity: true,
    };
  }
  const reason = view === undefined ? "no private work folder" : "no low-integrity launcher (Blender's Python was not found or the token could not be lowered)";
  return { command: blender, args: withCap, isolation: { ...base, filesystem: `not isolated (${reason})` }, gpu, writable: view?.writable ?? [], lowIntegrity: false };
}

function namespaceArgs(blender: string, view: View, gpu: boolean): string[] {
  const realBlender = realPath(blender);
  const readOnly = [...SYSTEM_READ_ONLY, posix.dirname(realBlender), ...view.readOnly.map(realPath)];
  const writable = [...view.writable.map(realPath), ...(gpu ? GPU_DEVICES : [])];
  return [...NAMESPACE_FLAGS, "sh", MOUNT_SCRIPT, posix.join(realPath(view.workDir), NEW_ROOT), ...writable, "--", ...readOnly, "--"];
}

export function planSandbox(blender: string, script: string, scriptArgs: string[], limits: Limits, tools: Tools, device: SandboxDevice = "cpu", view?: View): Plan {
  const gpu = device === "gpu";
  const blenderArgs = [...BLENDER_FLAGS, ...blenderThreadArguments(), "--python", script, "--", ...scriptArgs];
  const memoryMb = Math.floor(limits.memoryBytes / (1024 * 1024));
  const withCap = [...blenderArgs, "--memory-mb", String(memoryMb)];
  if (tools.platform === "win32") return windowsPlan(blender, withCap, limits, tools, gpu, view);
  if (gpu) withCap.push("--memory-kind", "data");
  const limit = gpu ? `--data=${limits.memoryBytes}` : `--as=${limits.memoryBytes}`;
  const kind = gpu ? "data segment" : "address space";
  const isolated = tools.mountNamespace === true && view !== undefined;
  const program = isolated ? realPath(blender) : blender;
  const prefix: string[] = [];
  if (tools.prlimit) prefix.push("prlimit", limit, "--core=0", "--");
  prefix.push(program, ...withCap);
  const network = tools.unshare ? "isolated" : "not isolated";
  const memory = `${tools.prlimit ? "prlimit" : "setrlimit"} ${kind}, ${memoryMb} MB`;
  const writable = view?.writable ?? [];
  if (isolated) {
    const isolation: Isolation = {
      network: "isolated",
      memory,
      timeoutMs: limits.timeoutMs,
      platform: tools.platform,
      filesystem: "mount namespace: read-only system and Blender, read-only delivery, private writable work folder and /tmp",
      processes: "own PID namespace",
    };
    return { command: "unshare", args: [...namespaceArgs(blender, view, gpu), ...prefix], isolation, gpu, writable, lowIntegrity: false };
  }
  const reason = view === undefined ? "no private work folder" : "unshare cannot create a user and mount namespace here";
  const isolation: Isolation = { network, memory, timeoutMs: limits.timeoutMs, platform: tools.platform, filesystem: `not isolated (${reason})`, processes: "shared PID namespace" };
  if (tools.unshare) return { command: "unshare", args: ["-rn", ...prefix], isolation, gpu, writable, lowIntegrity: false };
  const [command, ...args] = prefix;
  return { command: command ?? blender, args, isolation, gpu, writable, lowIntegrity: false };
}

export function sandboxEnvironment(home: string, gpu = false): NodeJS.ProcessEnv {
  const keep = ["PATH", "Path", "SystemRoot", "SYSTEMROOT", "windir", "LANG"];
  const environment: NodeJS.ProcessEnv = {};
  for (const name of keep) if (process.env[name] !== undefined) environment[name] = process.env[name];
  for (const name of ["BLENDER_USER_RESOURCES", "BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES", "BLENDER_USER_EXTENSIONS"]) {
    const folder = join(home, name.toLowerCase());
    mkdirSync(folder, { recursive: true });
    environment[name] = folder;
  }
  Object.assign(environment, { HOME: home, USERPROFILE: home, TEMP: home, TMP: home, TMPDIR: home });
  if (!gpu) Object.assign(environment, { CUDA_VISIBLE_DEVICES: "", HIP_VISIBLE_DEVICES: "" });
  return environment;
}

export function lowerIntegrity(folder: string): void {
  const result = spawnSync("icacls", [folder, "/setintegritylevel", "(OI)(CI)L"], { stdio: "ignore", windowsHide: true, timeout: 20_000 });
  if (result.status !== 0) throw new Error(`could not give ${folder} a low integrity label for the sandbox`);
}

export async function runSandboxed(plan: Plan, workDir: string): Promise<RunResult> {
  for (const folder of plan.writable) mkdirSync(folder, { recursive: true });
  if (plan.lowIntegrity) for (const folder of plan.writable) lowerIntegrity(folder);
  const home = mkdtempSync(join(plan.writable[0] ?? tmpdir(), "blendworks-sandbox-"));
  if (plan.command === "unshare" && plan.args[0] === NAMESPACE_FLAGS[0]) mkdirSync(join(realPath(workDir), NEW_ROOT), { recursive: true });
  try {
    return await new Promise<RunResult>((resolve, reject) => {
      const child = spawn(plan.command, plan.args, {
        cwd: workDir,
        env: sandboxEnvironment(home, plan.gpu),
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
