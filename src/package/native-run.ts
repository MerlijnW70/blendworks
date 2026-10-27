import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, posix } from "node:path";
import { LOW_INTEGRITY_SCRIPT, MOUNT_SCRIPT, NAMESPACE_FLAGS, SYSTEM_READ_ONLY, realPath, runSandboxed, type Isolation, type Limits, type Plan, type Tools } from "../judge/sandbox.js";

const MEGABYTE = 1024 * 1024;
const NEW_ROOT = ".sandbox-root";
const ENTER_WORK_FOLDER = "cd \"$1\" && shift && exec \"$@\"";
const JOB_PROCESS_MEMORY = 0x100;
const JOB_ACTIVE_PROCESS = 0x8;

export const WINDOWS_LAUNCHER = `
import ctypes, importlib.util, sys
spec = importlib.util.spec_from_file_location("low_integrity", sys.argv[1])
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
limit = int(sys.argv[2])
def capped_job(kernel32):
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        launcher.fail("CreateJobObjectW")
    limits = launcher.ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = launcher.KILL_ON_JOB_CLOSE | ${JOB_PROCESS_MEMORY} | ${JOB_ACTIVE_PROCESS}
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = limit
    if not kernel32.SetInformationJobObject(job, launcher.EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)):
        launcher.fail("SetInformationJobObject")
    return job
launcher.kill_on_close_job = capped_job
sys.exit(launcher.launch(sys.argv[3:]))
`;

export type NativeRequest = {
  binary: string;
  args: string[];
  limits: Limits;
  tools: Tools;
  input?: { name: string; data: Uint8Array };
  output?: string;
};

export type NativeResult = { code: number | null; signal: NodeJS.Signals | null; timedOut: boolean; log: string; output: Uint8Array | null; isolation: Isolation };

export type NativeRunner = (request: NativeRequest) => Promise<NativeResult>;

function windowsPlan(binary: string, args: string[], limits: Limits, tools: Tools, workDir: string): Plan {
  const memoryMb = Math.floor(limits.memoryBytes / MEGABYTE);
  const base = { network: "not isolated" as const, timeoutMs: limits.timeoutMs, platform: "windows" };
  const python = tools.lowIntegrityPython;
  if (python === undefined || python === null) {
    const isolation: Isolation = { ...base, memory: "not capped", filesystem: "not isolated (no low-integrity launcher: Blender's Python was not found or the token could not be lowered)", processes: "not isolated" };
    return { command: binary, args, isolation, gpu: false, writable: [workDir], lowIntegrity: false };
  }
  const isolation: Isolation = {
    ...base,
    memory: `job object, ${memoryMb} MB per process`,
    filesystem: "low integrity: writes only to the private work folder; reads are not limited",
    processes: "job object, one process, killed with the job",
  };
  return { command: python, args: ["-I", "-c", WINDOWS_LAUNCHER, LOW_INTEGRITY_SCRIPT, String(limits.memoryBytes), binary, ...args], isolation, gpu: false, writable: [workDir], lowIntegrity: true };
}

export function planNative(binary: string, args: string[], limits: Limits, tools: Tools, workDir: string): Plan {
  if (tools.platform === "win32") return windowsPlan(binary, args, limits, tools, workDir);
  const memoryMb = Math.floor(limits.memoryBytes / MEGABYTE);
  const prefix = tools.prlimit ? ["prlimit", `--as=${limits.memoryBytes}`, "--core=0", "--"] : [];
  const memory = `${tools.prlimit ? "prlimit" : "no limit tool: not capped"} address space, ${memoryMb} MB`;
  const writable = [workDir];
  if (tools.mountNamespace === true) {
    const real = realPath(binary);
    const readOnly = [...SYSTEM_READ_ONLY, posix.dirname(real)];
    const isolation: Isolation = {
      network: "isolated",
      memory,
      timeoutMs: limits.timeoutMs,
      platform: tools.platform,
      filesystem: "mount namespace: read-only system and tool, private writable work folder and /tmp",
      processes: "own PID namespace",
    };
    const root = posix.join(realPath(workDir), NEW_ROOT);
    return { command: "unshare", args: [...NAMESPACE_FLAGS, "sh", MOUNT_SCRIPT, root, realPath(workDir), "--", ...readOnly, "--", "sh", "-c", ENTER_WORK_FOLDER, "sh", realPath(workDir), ...prefix, real, ...args], isolation, gpu: false, writable, lowIntegrity: false };
  }
  const reason = "unshare cannot create a user and mount namespace here";
  const isolation: Isolation = { network: tools.unshare ? "isolated" : "not isolated", memory, timeoutMs: limits.timeoutMs, platform: tools.platform, filesystem: `not isolated (${reason})`, processes: "shared PID namespace" };
  if (tools.unshare) return { command: "unshare", args: ["-rn", ...prefix, binary, ...args], isolation, gpu: false, writable, lowIntegrity: false };
  const [command, ...rest] = [...prefix, binary, ...args];
  return { command: command ?? binary, args: rest, isolation, gpu: false, writable, lowIntegrity: false };
}

export const runNative: NativeRunner = async (request) => {
  const workDir = mkdtempSync(join(tmpdir(), "blendworks-native-"));
  try {
    if (request.input !== undefined) writeFileSync(join(workDir, request.input.name), request.input.data);
    const plan = planNative(request.binary, request.args, request.limits, request.tools, workDir);
    const result = await runSandboxed(plan, workDir);
    const produced = request.output === undefined ? null : join(workDir, request.output);
    const output = produced !== null && existsSync(produced) ? new Uint8Array(readFileSync(produced)) : null;
    return { code: result.code, signal: result.signal, timedOut: result.timedOut, log: result.output, output, isolation: plan.isolation };
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
};
