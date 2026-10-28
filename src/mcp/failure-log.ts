export const DEAD_AFTER_FAILURES = 3;
export const FAILURE_WINDOW_MS = 300_000;
export const DEAD_COOLDOWN_MS = 60_000;
export const BLENDER_FIX = "Check that BLENDER points to a working Blender (npm run doctor shows what is found)";

export interface FailureLimits {
  deadAfterFailures?: number | undefined;
  failureWindowMs?: number | undefined;
  deadCooldownMs?: number | undefined;
}

function seconds(ms: number): string {
  return `${Math.round(ms / 100) / 10} s`;
}

export class FailureLog {
  private failures: number[] = [];
  private reason: string | undefined;
  private until = 0;

  constructor(private readonly limits: FailureLimits = {}) {}

  clear(): void {
    this.failures = [];
  }

  dead(now: number): string | undefined {
    if (this.reason === undefined) return undefined;
    const left = this.until - now;
    if (left <= 0) {
      this.reason = undefined;
      this.failures = [];
      return undefined;
    }
    return `${this.reason} The server will not try again for ${Math.ceil(left / 1000)} s; fix BLENDER, or restart the MCP server.`;
  }

  note(reason: string, now: number): string {
    const window = this.limits.failureWindowMs ?? FAILURE_WINDOW_MS;
    this.failures = [...this.failures.filter((at) => now - at < window), now];
    if (this.failures.length < (this.limits.deadAfterFailures ?? DEAD_AFTER_FAILURES)) {
      return `${reason}. ${BLENDER_FIX}; the next call tries again.`;
    }
    this.reason = `${reason}; ${this.failures.length} restarts have failed within ${seconds(window)}. ${BLENDER_FIX}.`;
    this.until = now + (this.limits.deadCooldownMs ?? DEAD_COOLDOWN_MS);
    return this.dead(now) ?? this.reason;
  }
}
