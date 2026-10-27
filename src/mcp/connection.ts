import { type BridgeArgs, BridgeError, type BridgeLink } from "./protocol.js";

export const DEFAULT_TIMEOUT_MS = 120_000;
export const SLOW_TIMEOUT_MS = 300_000;
export const BAKE_TIMEOUT_MS = 660_000;
const SLOW_COMMANDS = new Set(["render_preview", "export", "import", "save_blend", "boolean", "decimate"]);

export function defaultTimeoutFor(cmd: string): number {
  if (cmd === "bake") return BAKE_TIMEOUT_MS;
  return SLOW_COMMANDS.has(cmd) ? SLOW_TIMEOUT_MS : DEFAULT_TIMEOUT_MS;
}

export interface ConnectionOptions {
  open: () => Promise<BridgeLink>;
  owned: boolean;
  label: string;
  timeoutFor?: (cmd: string) => number;
}

export interface CallOutcome {
  result: Record<string, unknown>;
  notices: string[];
}

class Timeout extends Error {}

function withNotices(error: unknown, notices: string[]): unknown {
  if (notices.length === 0 || !(error instanceof BridgeError)) return error;
  return new BridgeError(error.code, `${notices.join(" ")} ${error.message}`);
}

function seconds(ms: number): string {
  return `${Math.round(ms / 100) / 10} s`;
}

export class BridgeConnection {
  private link: BridgeLink | undefined;
  private lostReason: string | undefined;
  private deadReason: string | undefined;
  private queue: Promise<unknown> = Promise.resolve();
  private readonly timeoutFor: (cmd: string) => number;
  restarts = 0;

  constructor(private readonly options: ConnectionOptions, initial?: BridgeLink) {
    this.timeoutFor = options.timeoutFor ?? defaultTimeoutFor;
    if (initial !== undefined) this.adopt(initial);
  }

  get label(): string {
    return this.options.label;
  }

  async connect(): Promise<void> {
    if (this.link !== undefined) return;
    try {
      this.adopt(await this.options.open());
    } catch (error) {
      throw new BridgeError("disconnected", `cannot start ${this.label}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  request(cmd: string, args: BridgeArgs): Promise<CallOutcome> {
    const turn = this.queue.then(() => this.run(cmd, args));
    this.queue = turn.catch(() => undefined);
    return turn;
  }

  async close(): Promise<void> {
    const link = this.link;
    this.link = undefined;
    this.deadReason = "the connection was closed";
    await this.queue;
    if (link !== undefined) await link.close();
  }

  private adopt(link: BridgeLink): void {
    this.link = link;
    this.lostReason = undefined;
    link.onClose((reason) => {
      if (this.link === link) this.lostReason = reason;
    });
  }

  private async run(cmd: string, args: BridgeArgs): Promise<CallOutcome> {
    if (this.deadReason !== undefined) throw new BridgeError("disconnected", this.deadReason);
    const notices: string[] = [];
    if (this.link === undefined || this.lostReason !== undefined) notices.push(await this.recoverBeforeCall());
    const link = this.link;
    if (link === undefined) throw new BridgeError("disconnected", `${this.label} is not connected`);
    const timeoutMs = this.timeoutFor(cmd);
    try {
      const result = await this.callWithin(link, cmd, args, timeoutMs);
      return { result, notices };
    } catch (error) {
      throw withNotices(await this.recoverFrom(error, link, cmd, timeoutMs).catch((failure: unknown) => failure), notices);
    }
  }

  private async recoverFrom(error: unknown, link: BridgeLink, cmd: string, timeoutMs: number): Promise<unknown> {
    if (error instanceof Timeout) return new BridgeError("timeout", await this.recoverAfterTimeout(link, cmd, timeoutMs));
    if (error instanceof BridgeError && error.code === "disconnected" && this.link === link) {
      return new BridgeError("crashed", await this.recoverAfterCrash(link, cmd, error.message));
    }
    return error;
  }

  private callWithin(link: BridgeLink, cmd: string, args: BridgeArgs, timeoutMs: number): Promise<Record<string, unknown>> {
    let timer: NodeJS.Timeout | undefined;
    const late = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Timeout()), timeoutMs);
    });
    return Promise.race([link.call(cmd, args), late]).finally(() => clearTimeout(timer));
  }

  private async recoverBeforeCall(): Promise<string> {
    const reason = this.lostReason ?? "it was not connected";
    const stale = this.link;
    this.link = undefined;
    if (stale !== undefined) await stale.close().catch(() => undefined);
    if (this.options.owned) {
      await this.restart(`The Blender session had stopped (${reason})`);
      return `The Blender session had stopped (${reason}). Started a fresh session; the scene is empty, so rebuild it before continuing.`;
    }
    await this.reconnect();
    return `Reconnected to ${this.label}.`;
  }

  private async recoverAfterCrash(link: BridgeLink, cmd: string, reason: string): Promise<string> {
    this.link = undefined;
    await link.close().catch(() => undefined);
    const what = `Blender stopped while running ${cmd} (${reason})`;
    if (!this.options.owned) return `${what}. The next request reconnects to ${this.label}.`;
    await this.restart(what);
    return `${what}. Restarted the session once; the scene is empty now, so rebuild it before continuing.`;
  }

  private async recoverAfterTimeout(link: BridgeLink, cmd: string, timeoutMs: number): Promise<string> {
    this.link = undefined;
    await link.close().catch(() => undefined);
    const what = `${cmd} got no reply within ${seconds(timeoutMs)}`;
    if (!this.options.owned) return `${what}. Desktop Blender may still be busy; the next request reconnects to it.`;
    await this.restart(what);
    return `${what}. Stopped the stuck session and restarted it once; the scene is empty now, so rebuild it before continuing.`;
  }

  private async restart(what: string): Promise<void> {
    try {
      this.adopt(await this.options.open());
      this.restarts += 1;
    } catch (error) {
      this.link = undefined;
      this.deadReason = `${what}, and a fresh session failed to start: ${error instanceof Error ? error.message : String(error)}`;
      throw new BridgeError("crashed", this.deadReason);
    }
  }

  private async reconnect(): Promise<void> {
    try {
      this.adopt(await this.options.open());
    } catch (error) {
      this.link = undefined;
      throw new BridgeError("disconnected", `cannot reach ${this.label}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}
