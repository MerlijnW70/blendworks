import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { blenderPath } from "./blender.js";
import { type BridgeReply, readLine } from "./mcp/protocol.js";

export const SESSION_SCRIPT = fileURLToPath(new URL("../bridge/session.py", import.meta.url));

export type BridgeResult = Record<string, unknown>;

export type { BridgeReply };

export interface SessionOptions {
  workspace?: string;
  allowPython?: boolean;
  blender?: string;
  timeoutMs?: number;
  env?: NodeJS.ProcessEnv;
  autosaveSeconds?: number | "off";
  onStderr?: (line: string) => void;
  onDropped?: (message: string) => void;
  readyTimeoutMs?: number;
  args?: string[];
}

export interface RequestOptions {
  timeoutMs?: number;
}

export interface SessionExit {
  code: number | null;
  signal: NodeJS.Signals | null;
}

export class BridgeCommandError extends Error {
  readonly code: string;
  readonly command: string;

  constructor(command: string, failure: { code: string; message: string }) {
    super(`${command}: ${failure.code}: ${failure.message}`);
    this.name = "BridgeCommandError";
    this.code = failure.code;
    this.command = command;
  }
}

export type SessionErrorKind = "start" | "exited" | "timeout" | "protocol";

export class SessionError extends Error {
  constructor(
    message: string,
    readonly kind: SessionErrorKind = "start",
  ) {
    super(message);
    this.name = "SessionError";
  }
}

export interface Session {
  readonly pid: number | undefined;
  readonly workspace: string;
  readonly exited: Promise<SessionExit>;
  send(cmd: string, args?: BridgeResult, options?: RequestOptions): Promise<BridgeReply>;
  call(cmd: string, args?: BridgeResult, options?: RequestOptions): Promise<BridgeResult>;
  stderrTail(): string;
  close(graceMs?: number): Promise<SessionExit>;
  kill(): Promise<SessionExit>;
}

interface Pending {
  resolve: (reply: BridgeReply) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
}

const DEFAULT_TIMEOUT_MS = 120_000;
const STDERR_TAIL = 8_000;
const FORCE_KILL_MS = 2_000;
export const AUTOSAVE_ENV = "BLENDWORKS_AUTOSAVE_SECONDS";

function sessionEnvironment(options: SessionOptions): NodeJS.ProcessEnv {
  const env = { ...(options.env ?? process.env) };
  if (options.autosaveSeconds !== undefined) env[AUTOSAVE_ENV] = String(options.autosaveSeconds);
  return env;
}

export function sessionArguments(workspace: string, allowPython: boolean): string[] {
  const args = ["--background", "--factory-startup", "--python-exit-code", "1", "--python", SESSION_SCRIPT, "--", "--workspace", workspace];
  return allowPython ? [...args, "--allow-python"] : args;
}

const liveChildren = new Set<ChildProcessWithoutNullStreams>();

export function killLiveSessions(): void {
  for (const child of liveChildren) child.kill();
  liveChildren.clear();
}

async function becomeReady(session: BlenderSession, timeoutMs: number): Promise<void> {
  try {
    await session.call("describe", {}, { timeoutMs });
  } catch (error) {
    await session.kill();
    const tail = session.stderrTail().slice(-1500).trim();
    const cause = error instanceof SessionError && error.kind === "timeout" ? `the bridge did not answer within ${Math.round(timeoutMs / 100) / 10} s` : error instanceof Error ? error.message : String(error);
    throw new SessionError(`Blender started but the bridge never became ready: ${cause}${tail === "" ? "" : `; its last output:
${tail}`}`, "start");
  }
}

export async function startSession(options: SessionOptions = {}): Promise<Session> {
  const workspace = resolve(options.workspace ?? "workspace");
  const child = spawn(options.blender ?? blenderPath(), options.args ?? sessionArguments(workspace, options.allowPython ?? false), {
    env: sessionEnvironment(options),
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  await new Promise<void>((resolveSpawn, rejectSpawn) => {
    child.once("spawn", () => resolveSpawn());
    child.once("error", (error) => rejectSpawn(new SessionError(`could not start Blender: ${error.message}`)));
  });
  const session = new BlenderSession(child, workspace, options);
  if (options.readyTimeoutMs !== undefined) await becomeReady(session, options.readyTimeoutMs);
  return session;
}

class BlenderSession implements Session {
  readonly workspace: string;
  readonly exited: Promise<SessionExit>;
  private readonly child: ChildProcessWithoutNullStreams;
  private readonly pending = new Map<number, Pending>();
  private readonly timeoutMs: number;
  private readonly onDropped: (message: string) => void;
  private nextId = 0;
  private stderr = "";
  private exit: SessionExit | undefined;

  constructor(child: ChildProcessWithoutNullStreams, workspace: string, options: SessionOptions) {
    this.child = child;
    this.workspace = workspace;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.onDropped = options.onDropped ?? (() => undefined);
    liveChildren.add(child);
    this.exited = new Promise((resolveExit) => {
      child.once("exit", (code, signal) => {
        liveChildren.delete(child);
        this.exit = { code, signal };
        this.failAll(new SessionError(`Blender exited (code ${code}, signal ${signal}): ${this.stderrTail().slice(-2000)}`, "exited"));
        resolveExit(this.exit);
      });
    });
    child.stdin.on("error", () => undefined);
    createInterface({ input: child.stdout }).on("line", (line) => this.receive(line));
    createInterface({ input: child.stderr }).on("line", (line) => {
      this.stderr = (this.stderr + line + "\n").slice(-STDERR_TAIL);
      options.onStderr?.(line);
    });
  }

  get pid(): number | undefined {
    return this.child.pid;
  }

  stderrTail(): string {
    return this.stderr;
  }

  send(cmd: string, args: BridgeResult = {}, options: RequestOptions = {}): Promise<BridgeReply> {
    if (this.exit) return Promise.reject(new SessionError(`the session has exited (code ${this.exit.code})`, "exited"));
    this.nextId += 1;
    const id = this.nextId;
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    return new Promise<BridgeReply>((resolveReply, rejectReply) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectReply(new SessionError(`${cmd} timed out after ${timeoutMs} ms`, "timeout"));
      }, timeoutMs);
      this.pending.set(id, { resolve: resolveReply, reject: rejectReply, timer });
      this.child.stdin.write(`${JSON.stringify({ id, cmd, args })}\n`);
    });
  }

  async call(cmd: string, args: BridgeResult = {}, options: RequestOptions = {}): Promise<BridgeResult> {
    const reply = await this.send(cmd, args, options);
    if (!reply.ok) throw new BridgeCommandError(cmd, reply.error);
    return reply.result;
  }

  async close(graceMs = 10_000): Promise<SessionExit> {
    if (this.exit) return this.exit;
    this.child.stdin.end(`${JSON.stringify({ id: "quit", cmd: "quit" })}\n`);
    const timer = setTimeout(() => void this.kill(), graceMs);
    const exit = await this.exited;
    clearTimeout(timer);
    return exit;
  }

  async kill(): Promise<SessionExit> {
    if (this.exit) return this.exit;
    this.child.kill();
    const force = setTimeout(() => this.child.kill("SIGKILL"), FORCE_KILL_MS);
    const exit = await this.exited;
    clearTimeout(force);
    return exit;
  }

  private receive(raw: string): void {
    const line = readLine(raw);
    if (line.kind === "ignored") return;
    if (line.kind === "garbled") {
      const waiting = line.id === undefined ? undefined : this.pending.get(line.id);
      if (waiting === undefined || line.id === undefined) {
        this.stderr = (this.stderr + `unparsed stdout: ${raw}
`).slice(-STDERR_TAIL);
        this.onDropped(`dropped an unreadable bridge line (${line.error.message})`);
        return;
      }
      this.pending.delete(line.id);
      clearTimeout(waiting.timer);
      waiting.reject(new SessionError(line.error.message, "protocol"));
      return;
    }
    const waiting = this.pending.get(line.reply.id);
    if (!waiting) {
      this.onDropped(`dropped a bridge reply for request ${line.reply.id}, which nobody is waiting for`);
      return;
    }
    this.pending.delete(line.reply.id);
    clearTimeout(waiting.timer);
    waiting.resolve(line.reply);
  }

  private failAll(error: Error): void {
    for (const waiting of this.pending.values()) {
      clearTimeout(waiting.timer);
      waiting.reject(error);
    }
    this.pending.clear();
  }
}
