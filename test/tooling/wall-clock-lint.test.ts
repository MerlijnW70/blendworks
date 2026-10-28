import { describe, expect, it } from "vitest";
import { offendingFiles, WALL_CLOCK_ALLOWED, wallClockBounds } from "../../scripts/lib/wall-clock-lint.js";
import { waitFor } from "../setup/wait-for.js";

describe("wall-clock bounds in tests", () => {
  it("are refused outside the allow-list: CPU contention breaks them, so wait for a condition or inject a clock instead", () => {
    const offenders = Object.entries(offendingFiles()).filter(([file]) => WALL_CLOCK_ALLOWED[file] === undefined);
    expect(offenders.map(([file, bounds]) => `${file}: ${bounds.map((bound) => `line ${bound.line}: ${bound.text}`).join("; ")}`)).toEqual([]);
  });

  it("keeps no allow-list entry for a file that no longer has such a bound", () => {
    const offending = Object.keys(offendingFiles());
    expect(Object.keys(WALL_CLOCK_ALLOWED).filter((file) => !offending.includes(file))).toEqual([]);
  });

  it("finds a bound on elapsed milliseconds, seconds or a duration, in any of the usual spellings", () => {
    const lines = [
      "expect(performance.now() - started).toBeLessThan(500);",
      "expect(Date.now() - started).toBeLessThanOrEqual(MAX_MS);",
      "expect(probe.seconds).toBeLessThan(BEFORE.seconds / 4);",
      "expect(run.duration).toBeLessThan(3000);",
      "expect(elapsedMs).toBeLessThan(10);",
      "expect(clock.workMs()).toBeLessThan(200);",
    ];
    for (const line of lines) expect(wallClockBounds(line), line).toHaveLength(1);
    expect(wallClockBounds(lines.join("\n"))).toHaveLength(lines.length);
  });

  it("leaves bounds on counts, sizes and numeric error alone", () => {
    const lines = ["expect(packs).toBeLessThanOrEqual(12);", "expect(overlap).toBeLessThan(0.01);", "expect(Math.abs(own - sum) / own).toBeLessThan(1e-6);", "expect(polls).toBeLessThan(15);", "expect(elapsed).toBeGreaterThan(5);"];
    for (const line of lines) expect(wallClockBounds(line), line).toEqual([]);
  });

  it("offers waitFor(condition) for tests that need to wait for something", async () => {
    let ready = false;
    setTimeout(() => (ready = true), 20);
    await waitFor(() => ready, { description: "the flag" });
    expect(ready).toBe(true);
    await expect(waitFor(() => false, { timeoutMs: 30, description: "never" })).rejects.toThrow("timed out waiting for never after 30 ms");
  });
});
