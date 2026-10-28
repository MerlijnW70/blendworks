import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { describeChange, heaviestFirst, measuredDurationsPath, missingDurations, saveBaseline, scheduledFiles, UNMEASURED_SECONDS } from "../../scripts/lib/durations.js";
import { scratch } from "./probes.js";

function setup(baseline: Record<string, number>, measured: Record<string, number>): { root: string; baselinePath: string } {
  const root = scratch("durations");
  const baselinePath = join(root, "baseline.json");
  writeFileSync(baselinePath, JSON.stringify(baseline));
  mkdirSync(join(root, "timings"), { recursive: true });
  writeFileSync(measuredDurationsPath(root), JSON.stringify(measured));
  return { root, baselinePath };
}

describe("the duration baseline", () => {
  it("is refreshed with entries for new test files and without the entries of deleted ones", () => {
    const { root, baselinePath } = setup({ "test/old.test.ts": 5, "test/gone.test.ts": 9, "test/kept.test.ts": 2 }, { "test/new.test.ts": 12.5, "test/kept.test.ts": 3, "test/removed-too.test.ts": 1 });
    const change = saveBaseline(root, baselinePath, ["test/old.test.ts", "test/kept.test.ts", "test/new.test.ts", "test/skipped.test.ts"]);
    expect(JSON.parse(readFileSync(baselinePath, "utf8"))).toEqual({ "test/kept.test.ts": 3, "test/new.test.ts": 12.5, "test/old.test.ts": 5, "test/skipped.test.ts": UNMEASURED_SECONDS });
    expect(change.added).toEqual(["test/new.test.ts", "test/skipped.test.ts"]);
    expect(change.dropped).toEqual(["test/gone.test.ts"]);
    expect(describeChange(change).join("\n")).toContain("had no entry: test/new.test.ts, test/skipped.test.ts");
  });

  it("does not make a test fail for a file without an entry: the scheduler starts unknown files first", () => {
    expect(missingDurations(["test/a.test.ts", "test/c.test.ts"], { "test/a.test.ts": 1.5 })).toEqual(["test/c.test.ts"]);
    const order = heaviestFirst(["test/a.test.ts", "test/unknown.test.ts", "test/b.test.ts"], (file) => file, { "test/a.test.ts": 1, "test/b.test.ts": 30 }, () => Number.POSITIVE_INFINITY);
    expect(order).toEqual(["test/unknown.test.ts", "test/b.test.ts", "test/a.test.ts"]);
  });

  it("finds every vitest file and every bridge test file", () => {
    const files = scheduledFiles();
    expect(files).toContain("test/tooling/durations.test.ts");
    expect(files).toContain("bridge/tests/test_engrave_many.py");
    expect(files.some((file) => file.includes("node_modules") || file.endsWith("helpers.py"))).toBe(false);
  });
});
