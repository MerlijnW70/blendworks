import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { blenderPath } from "./blender.js";

export const SESSION_SCRIPT = fileURLToPath(new URL("../bridge/session.py", import.meta.url));

export type BridgeErrorCode = "bad_args" | "not_found" | "failed" | "forbidden";
export type BridgeResult = Record<string, unknown>;
export type BridgeId = number | string | null;

export interface BridgeFailure {
  code: BridgeErrorCode;
  message: string;
}

export type BridgeReply =
  | { id: BridgeId; ok: true; result: BridgeResult }
  | { id: BridgeId; ok: false; error: BridgeFailure };

export interface SessionOptions {
  workspace?: string;
  allowPython?: boolean;
  blender?: string;
  timeoutMs?: number;
  env?: NodeJS.ProcessEnv;
  onStderr?: (line: string) => void;
}

export interface RequestOptions {
  timeoutMs?: number;
}

export interface SessionExit {
  code: number | null;
  signal: NodeJS.Signals | null;
}

export class BridgeCommandError extends Error {
  readonly code: BridgeErrorCode;
  readonly command: string;

  constructor(command: string, failure: BridgeFailure) {
    super(`${command}: ${failure.code}: ${failure.message}`);
    this.name = "BridgeCommandError";
    this.code = failure.code;
    this.command = command;
  }
}

export class SessionError extends Error {
  constructor(message: string) {
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
}

interface Pending {
  resolve: (reply: BridgeReply) => void;
  reject: (error: Error) => void;
  timer: NodeJS.Timeout;
}

const DEFAULT_TIMEOUT_MS = 120_000;
const STDERR_TAIL = 8_000;

export function sessionArguments(workspace: string, allowPython: boolean): string[] {
  const args = ["--background", "--factory-startup", "--python-exit-code", "1", "--python", SESSION_SCRIPT, "--", "--workspace", workspace];
  return allowPython ? [...args, "--allow-python"] : args;
}

export async function startSession(options: SessionOptions = {}): Promise<Session> {
  const workspace = resolve(options.workspace ?? "workspace");
  const child = spawn(options.blender ?? blenderPath(), sessionArguments(workspace, options.allowPython ?? false), {
    env: options.env ?? process.env,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
  await new Promise<void>((resolveSpawn, rejectSpawn) => {
    child.once("spawn", () => resolveSpawn());
    child.once("error", (error) => rejectSpawn(new SessionError(`could not start Blender: ${error.message}`)));
  });
  return new BlenderSession(child, workspace, options);
}

class BlenderSession implements Session {
  readonly workspace: string;
  readonly exited: Promise<SessionExit>;
  private readonly child: ChildProcessWithoutNullStreams;
  private readonly pending = new Map<number, Pending>();
  private readonly timeoutMs: number;
  private nextId = 0;
  private stderr = "";
  private exit: SessionExit | undefined;

  constructor(child: ChildProcessWithoutNullStreams, workspace: string, options: SessionOptions) {
    this.child = child;
    this.workspace = workspace;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.exited = new Promise((resolveExit) => {
      child.once("exit", (code, signal) => {
        this.exit = { code, signal };
        this.failAll(new SessionError(`Blender exited (code ${code}, signal ${signal}): ${this.stderrTail().slice(-2000)}`));
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
    if (this.exit) return Promise.reject(new SessionError(`the session has exited (code ${this.exit.code})`));
    this.nextId += 1;
    const id = this.nextId;
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    return new Promise<BridgeReply>((resolveReply, rejectReply) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        rejectReply(new SessionError(`${cmd} timed out after ${timeoutMs} ms`));
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
    const timer = setTimeout(() => this.child.kill(), graceMs);
    const exit = await this.exited;
    clearTimeout(timer);
    return exit;
  }

  private receive(line: string): void {
    let reply: BridgeReply;
    try {
      reply = JSON.parse(line) as BridgeReply;
    } catch {
      this.stderr = (this.stderr + `unparsed stdout: ${line}\n`).slice(-STDERR_TAIL);
      return;
    }
    if (typeof reply.id !== "number") return;
    const waiting = this.pending.get(reply.id);
    if (!waiting) return;
    this.pending.delete(reply.id);
    clearTimeout(waiting.timer);
    waiting.resolve(reply);
  }

  private failAll(error: Error): void {
    for (const waiting of this.pending.values()) {
      clearTimeout(waiting.timer);
      waiting.reject(error);
    }
    this.pending.clear();
  }
}
