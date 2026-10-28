import { BridgeError } from "./protocol.js";

export const BOOT_BACKOFF_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

export interface BootOptions<T> {
  start: () => Promise<T>;
  backoffMs?: number[];
  now?: () => number;
}

export class Boot<T> {
  private attempt: Promise<T> | undefined;
  private settled: { ok: true; value: T } | { ok: false; error: unknown; at: number } | undefined;
  private failures = 0;

  constructor(private readonly options: BootOptions<T>) {}

  get ready(): T | undefined {
    return this.settled?.ok === true ? this.settled.value : undefined;
  }

  private get now(): number {
    return (this.options.now ?? Date.now)();
  }

  start(): Promise<T> {
    if (this.attempt !== undefined) return this.attempt;
    const run = this.options.start().then(
      (value) => {
        this.settled = { ok: true, value };
        return value;
      },
      (error: unknown) => {
        this.failures += 1;
        this.settled = { ok: false, error, at: this.now };
        throw error;
      },
    );
    run.catch(() => undefined);
    this.attempt = run;
    return run;
  }

  async settle(limitMs: number): Promise<void> {
    if (this.attempt === undefined || this.settled !== undefined) return;
    let timer: NodeJS.Timeout | undefined;
    const late = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, limitMs);
    });
    try {
      await Promise.race([this.attempt.then(() => undefined, () => undefined), late]);
    } finally {
      clearTimeout(timer);
    }
  }

  private nextAttemptIn(): number {
    if (this.settled === undefined || this.settled.ok) return 0;
    const steps = this.options.backoffMs ?? BOOT_BACKOFF_MS;
    const wait = steps[Math.min(this.failures, steps.length) - 1] ?? 0;
    return Math.max(0, this.settled.at + wait - this.now);
  }

  async wait(limitMs: number, label: string): Promise<T> {
    if (this.settled?.ok === false) {
      const left = this.nextAttemptIn();
      if (left > 0) {
        const cause = this.settled.error instanceof Error ? this.settled.error.message : String(this.settled.error);
        throw new BridgeError("disconnected", `${cause} (the server tries to start ${label} again in ${Math.ceil(left / 1000)} s)`);
      }
      this.attempt = undefined;
      this.settled = undefined;
    }
    const attempt = this.start();
    let timer: NodeJS.Timeout | undefined;
    const late = new Promise<never>((_, reject) => {
      timer = setTimeout(
        () => reject(new BridgeError("timeout", `${label} is still starting after ${Math.round(limitMs / 100) / 10} s; it keeps starting in the background, so call again in a moment (pass timeout_seconds to wait longer for a slow cold start)`)),
        limitMs,
      );
    });
    try {
      return await Promise.race([attempt, late]);
    } finally {
      clearTimeout(timer);
    }
  }
}
