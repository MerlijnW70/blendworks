import { BLENDER_FIX, FailureLog } from "./failure-log.js";
import { type BridgeArgs, BridgeError, type BridgeLink } from "./protocol.js";
import { RECOVER_COMMAND, RECOVER_TIMEOUT_MS, recoverScene } from "./recovery.js";
import { type BridgeCommand, FALLBACK_TIMEOUT_MS } from "./schema.js";

export const PROGRESS_INTERVAL_MS = 10_000;
export const CLOSE_LIMIT_MS = 6_000;
export const RESTART_DELAYS_MS = [500, 2_000];

export interface ConnectionOptions {
  open: () => Promise<BridgeLink>;
  owned: boolean;
  label: string;
  timeoutFor?: (cmd: string) => number;
  progressIntervalMs?: number;
  closeLimitMs?: number;
  restartDelaysMs?: number[];
  deadAfterFailures?: number;
  failureWindowMs?: number;
  deadCooldownMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export interface Progress {
  state: "queued" | "running";
  cmd: string;
  elapsedMs: number;
  timeoutMs: number;
  ahead: number;
}

export interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
  onProgress?: (progress: Progress) => void;
}

export interface CallOutcome {
  result: Record<string, unknown>;
  notices: string[];
}

class Interrupt extends Error {}
class Timeout extends Interrupt {}
class Cancelled extends Interrupt {}
class Closed extends Interrupt {}

interface Job {
  cmd: string;
  args: BridgeArgs;
  options: RequestOptions;
  timeoutMs: number;
  queuedAt: number;
  startedAt: number | undefined;
  resolve: (outcome: CallOutcome) => void;
  reject: (error: unknown) => void;
  interrupt: (reason: Interrupt) => void;
  cleanup: () => void;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function withNotices(error: unknown, notices: string[]): unknown {
  if (notices.length === 0 || !(error instanceof BridgeError)) return error;
  return new BridgeError(error.code, `${notices.join(" ")} ${error.message}`);
}

function seconds(ms: number): string {
  return `${Math.round(ms / 100) / 10} s`;
}

function within<T>(work: Promise<T>, limitMs: number): Promise<T | undefined> {
  let timer: NodeJS.Timeout | undefined;
  const late = new Promise<undefined>((resolve) => {
    timer = setTimeout(() => resolve(undefined), limitMs);
  });
  return Promise.race([work, late]).finally(() => clearTimeout(timer));
}

export class BridgeConnection {
  private link: BridgeLink | undefined;
  private lostReason: string | undefined;
  private readonly failures: FailureLog;
  private readonly waiting: Job[] = [];
  private running: Job | undefined;
  private closing: Promise<void> | undefined;
  private timeouts = new Map<string, number>();
  private maxTimeouts = new Map<string, number>();
  private offersRecover = false;
  restarts = 0;

  constructor(private readonly options: ConnectionOptions, initial?: BridgeLink) {
    this.failures = new FailureLog(options);
    if (initial !== undefined) this.adopt(initial);
  }

  get label(): string {
    return this.options.label;
  }

  private get closeLimitMs(): number {
    return this.options.closeLimitMs ?? CLOSE_LIMIT_MS;
  }

  useCommands(commands: BridgeCommand[]): void {
    this.timeouts = new Map(commands.map((command) => [command.name, command.timeoutMs]));
    this.maxTimeouts = new Map(commands.map((command) => [command.name, command.maxTimeoutMs]));
    this.offersRecover = commands.some((command) => command.name === RECOVER_COMMAND);
  }

  timeoutFor(cmd: string): number {
    if (this.options.timeoutFor !== undefined) return this.options.timeoutFor(cmd);
    return this.timeouts.get(cmd) ?? FALLBACK_TIMEOUT_MS;
  }

  private get now(): number {
    return (this.options.now ?? Date.now)();
  }

  private pause(ms: number): Promise<void> {
    return (this.options.sleep ?? ((wait: number) => new Promise<void>((done) => setTimeout(done, wait))))(ms);
  }

  private dead(): string | undefined {
    return this.closing !== undefined ? "the connection was closed" : this.failures.dead(this.now);
  }

  async connect(): Promise<void> {
    if (this.link !== undefined) return;
    let link: BridgeLink;
    try {
      link = await this.options.open();
    } catch (error) {
      throw new BridgeError("disconnected", `cannot start ${this.label}: ${message(error)}. ${BLENDER_FIX}.`);
    }
    if (this.closing !== undefined) {
      await within(link.kill().catch(() => undefined), this.closeLimitMs);
      throw new BridgeError("disconnected", "the connection was closed");
    }
    this.adopt(link);
  }

  request(cmd: string, args: BridgeArgs, options: RequestOptions = {}): Promise<CallOutcome> {
    const dead = this.dead();
    if (dead !== undefined) return Promise.reject(new BridgeError("disconnected", dead));
    if (options.signal?.aborted) return Promise.reject(new BridgeError("cancelled", `${cmd} was cancelled before it started`));
    return new Promise<CallOutcome>((resolve, reject) => {
      const job = this.createJob(cmd, args, options, resolve, reject);
      this.waiting.push(job);
      this.pump();
    });
  }

  close(): Promise<void> {
    if (this.closing !== undefined) return this.closing;
    for (const job of this.waiting.splice(0)) job.reject(new BridgeError("disconnected", "the connection was closed before the request ran"));
    this.running?.interrupt(new Closed());
    const link = this.link;
    this.link = undefined;
    this.closing = within(link?.close().catch(() => undefined) ?? Promise.resolve(), this.closeLimitMs).then(() => undefined);
    return this.closing;
  }

  private createJob(cmd: string, args: BridgeArgs, options: RequestOptions, resolve: (outcome: CallOutcome) => void, reject: (error: unknown) => void): Job {
    const timeoutMs = options.timeoutMs ?? this.timeoutFor(cmd);
    let settled = false;
    let timer: NodeJS.Timeout | undefined;
    const job: Job = {
      cmd,
      args,
      options,
      timeoutMs,
      queuedAt: Date.now(),
      startedAt: undefined,
      resolve: (outcome) => {
        if (settled) return;
        settled = true;
        job.cleanup();
        resolve(outcome);
      },
      reject: (error) => {
        if (settled) return;
        settled = true;
        job.cleanup();
        reject(error);
      },
      interrupt: () => undefined,
      cleanup: () => {
        clearInterval(timer);
        options.signal?.removeEventListener("abort", onAbort);
      },
    };
    const onAbort = () => this.cancel(job);
    options.signal?.addEventListener("abort", onAbort, { once: true });
    if (options.onProgress !== undefined) {
      const report = options.onProgress;
      timer = setInterval(() => report(this.progressOf(job)), this.options.progressIntervalMs ?? PROGRESS_INTERVAL_MS);
      timer.unref();
    }
    return job;
  }

  private progressOf(job: Job): Progress {
    const position = this.waiting.indexOf(job);
    return {
      state: job.startedAt === undefined ? "queued" : "running",
      cmd: job.cmd,
      elapsedMs: Date.now() - job.queuedAt,
      timeoutMs: job.timeoutMs,
      ahead: position < 0 ? 0 : position + (this.running === undefined ? 0 : 1),
    };
  }

  private cancel(job: Job): void {
    const position = this.waiting.indexOf(job);
    if (position >= 0) {
      this.waiting.splice(position, 1);
      job.reject(new BridgeError("cancelled", `${job.cmd} was cancelled before it reached Blender`));
      return;
    }
    if (this.running === job) job.interrupt(new Cancelled());
  }

  private pump(): void {
    if (this.running !== undefined) return;
    const job = this.waiting.shift();
    if (job === undefined) return;
    this.running = job;
    void this.execute(job).finally(() => {
      this.running = undefined;
      this.pump();
    });
  }

  private adopt(link: BridgeLink): void {
    this.link = link;
    this.lostReason = undefined;
    link.onClose((reason) => {
      if (this.link === link) this.lostReason = reason;
    });
  }

  private async execute(job: Job): Promise<void> {
    const notices: string[] = [];
    try {
      const dead = this.dead();
      if (dead !== undefined) throw new BridgeError("disconnected", dead);
      if (this.link === undefined || this.lostReason !== undefined) notices.push(await this.recoverBeforeCall());
      const link = this.link;
      if (link === undefined) throw new BridgeError("disconnected", `${this.label} is not connected`);
      if (job.options.signal?.aborted) throw new BridgeError("cancelled", `${job.cmd} was cancelled before it reached Blender`);
      job.startedAt = Date.now();
      try {
        job.resolve({ result: await this.callWithin(link, job), notices });
      } catch (error) {
        throw await this.recoverFrom(error, link, job).catch((failure: unknown) => failure);
      }
    } catch (error) {
      job.reject(withNotices(error, notices));
    }
  }

  private callWithin(link: BridgeLink, job: Job): Promise<Record<string, unknown>> {
    let timer: NodeJS.Timeout | undefined;
    const stopped = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Timeout()), job.timeoutMs);
      job.interrupt = (reason) => reject(reason);
    });
    return Promise.race([link.call(job.cmd, job.args), stopped]).finally(() => {
      clearTimeout(timer);
      job.interrupt = () => undefined;
    });
  }

  private timeoutHint(cmd: string): string {
    const max = this.maxTimeouts.get(cmd);
    const limit = max === undefined ? "" : ` (at most ${seconds(max)} for ${cmd})`;
    return ` To wait longer, pass timeout_seconds${limit}.`;
  }

  private async recoverFrom(error: unknown, link: BridgeLink, job: Job): Promise<unknown> {
    if (error instanceof Closed) return new BridgeError("disconnected", `${job.cmd} was stopped because the connection was closed`);
    if (error instanceof Timeout) {
      return new BridgeError("timeout", `${await this.recoverAfterStop(link, `${job.cmd} got no reply within ${seconds(job.timeoutMs)}`, true)}${this.timeoutHint(job.cmd)}`);
    }
    if (error instanceof Cancelled) return new BridgeError("cancelled", await this.recoverAfterStop(link, `${job.cmd} was cancelled while it ran`, true));
    if (error instanceof BridgeError && error.code === "protocol") {
      return new BridgeError("protocol", await this.recoverAfterStop(link, `${job.cmd} got a reply that could not be read (${error.message})`, false));
    }
    if (error instanceof BridgeError && error.code === "disconnected" && this.link === link) {
      return new BridgeError("crashed", await this.recoverAfterCrash(link, job.cmd, error.message));
    }
    return error;
  }

  private async recoverBeforeCall(): Promise<string> {
    const reason = this.lostReason ?? "it was not connected";
    const stale = this.link;
    this.link = undefined;
    if (stale !== undefined) await stale.close().catch(() => undefined);
    if (this.options.owned) return `The Blender session had stopped (${reason}). ${await this.restartAndRecover(`The Blender session had stopped (${reason})`)}`;
    await this.reconnect();
    return `Reconnected to ${this.label}.`;
  }

  private async recoverAfterCrash(link: BridgeLink, cmd: string, reason: string): Promise<string> {
    this.link = undefined;
    await link.close().catch(() => undefined);
    const what = `Blender stopped while running ${cmd} (${reason})`;
    if (!this.options.owned) return `${what}. The next request reconnects to ${this.label}.`;
    return `${what}. ${await this.restartAndRecover(what)}`;
  }

  private async recoverAfterStop(link: BridgeLink, what: string, mayBeBusy: boolean): Promise<string> {
    this.link = undefined;
    if (!this.options.owned) {
      await link.close().catch(() => undefined);
      return `${what}. ${mayBeBusy ? "Desktop Blender may still be busy; the" : "The"} next request reconnects to ${mayBeBusy ? "it" : this.label}.`;
    }
    await within(link.kill().catch(() => undefined), this.closeLimitMs);
    return `${what}. Stopped the session. ${await this.restartAndRecover(what)}`;
  }

  private async restartAndRecover(what: string): Promise<string> {
    await this.restart(what);
    const link = this.link;
    if (!this.offersRecover || link === undefined) return "Started a fresh session; the scene is empty, so rebuild it before continuing.";
    try {
      return `Restarted it. ${await recoverScene(link, this.timeouts.get(RECOVER_COMMAND) ?? RECOVER_TIMEOUT_MS)}`;
    } catch (error) {
      if (error instanceof BridgeError && error.code !== "disconnected" && error.code !== "timeout") {
        return `Restarted it, but reloading the autosave failed (${error.message}); the scene is empty, so rebuild it before continuing.`;
      }
      this.link = undefined;
      await within(link.kill().catch(() => undefined), this.closeLimitMs);
      await this.restart(`${what}, and reloading the autosave failed too`);
      return `Restarted it, but reloading the autosave failed (${message(error)}); started an empty session instead. The autosave is still in .blendworks/ for blender_load_blend.`;
    }
  }

  private async restart(what: string): Promise<void> {
    const delays = this.options.restartDelaysMs ?? RESTART_DELAYS_MS;
    let failure: unknown;
    for (let attempt = 0; attempt <= delays.length; attempt += 1) {
      if (this.closing !== undefined) throw new BridgeError("disconnected", "the connection was closed");
      try {
        const link = await this.options.open();
        if (this.closing !== undefined) {
          await within(link.kill().catch(() => undefined), this.closeLimitMs);
          throw new BridgeError("disconnected", "the connection was closed");
        }
        this.adopt(link);
        this.restarts += 1;
        this.failures.clear();
        return;
      } catch (error) {
        if (error instanceof BridgeError && error.code === "disconnected" && this.closing !== undefined) throw error;
        failure = error;
        const wait = delays[attempt];
        if (wait !== undefined) await this.pause(wait);
      }
    }
    this.link = undefined;
    throw new BridgeError("crashed", this.failures.note(`${what}, and a fresh session failed to start after ${delays.length + 1} attempt${delays.length === 0 ? "" : "s"}: ${message(failure)}`, this.now));
  }

  private async reconnect(): Promise<void> {
    try {
      this.adopt(await this.options.open());
    } catch (error) {
      this.link = undefined;
      throw new BridgeError("disconnected", `cannot reach ${this.label}: ${message(error)}`);
    }
  }
}
