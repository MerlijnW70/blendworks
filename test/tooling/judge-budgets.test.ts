import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { EXEMPT_FILES } from "../../scripts/lib/file-limits.js";
import { waitStarted } from "../../scripts/lib/locks.js";
import { repoRoot } from "../../scripts/lib/paths.js";
import { startWorkClock, useTimers, type Timers, WorkTimeout } from "../setup/work-clock.js";

const EQUIVALENCE = "test/judge/equivalence.test.ts";

function fakeTimers(): Timers & { advance(ms: number): void } {
  let time = 1_000;
  const pending: { at: number; run: () => void }[] = [];
  return {
    now: () => time,
    after(ms, run) {
      const entry = { at: time + ms, run };
      pending.push(entry);
      return () => {
        const index = pending.indexOf(entry);
        if (index >= 0) pending.splice(index, 1);
      };
    },
    advance(ms) {
      const target = time + ms;
      for (;;) {
        const due = pending.filter((entry) => entry.at <= target).sort((a, b) => a.at - b.at)[0];
        if (due === undefined) break;
        pending.splice(pending.indexOf(due), 1);
        time = due.at;
        due.run();
      }
      time = target;
    },
  };
}

describe("the equivalence test's budgets count work per judge run, not waiting", () => {
  it("gives each judge run its own work budget, inside a test budget that grows with the stored fixtures", () => {
    const source = readFileSync(join(repoRoot, EQUIVALENCE), "utf8");
    expect(source).toMatch(/underWorkClock\(`equivalence case \$\{entry\.id\}`, CASE_WORK_MS,/);
    expect(source).toMatch(/workBudget\(Object\.keys\(STORED\)\.length \* CASE_WORK_MS\)/);
    expect(EXEMPT_FILES[EQUIVALENCE]).toMatch(/own work budget/);
  });

  it("lets a run wait for slots far past its budget, and stops a run that hangs while working, by its own name", async () => {
    const timers = fakeTimers();
    const restore = useTimers(timers);
    try {
      const whole = startWorkClock("the equivalence test", 120 * 60_000);
      const run = startWorkClock("equivalence case crate", 60_000);
      let failed: unknown;
      run.expired.catch((error: unknown) => (failed = error));
      const waited = waitStarted();
      timers.advance(20 * 60_000);
      waited();
      await Promise.resolve();
      timers.advance(59_999);
      await Promise.resolve();
      expect(failed).toBeUndefined();
      timers.advance(1);
      await Promise.resolve();
      expect(failed).toBeInstanceOf(WorkTimeout);
      expect((failed as WorkTimeout).message).toMatch(/equivalence case crate .* worked 60\.0 s, over its work budget of 60 s; it also waited 1200\.0 s/);
      expect(whole.workMs()).toBe(60_000);
      run.stop();
      whole.stop();
    } finally {
      restore();
    }
  });
});
