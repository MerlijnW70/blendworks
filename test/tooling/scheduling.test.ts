import { describe, expect, it } from "vitest";
import { bridgeDurations, timeoutLine } from "../../scripts/lib/bridge-runner.js";
import { knownDurations } from "../../scripts/lib/durations.js";
import { defaultStress, loadScript, parseStress } from "../../scripts/lib/stress.js";
import { timingReport, type Timing } from "../../scripts/lib/timings.js";
import { heaviestFirst } from "../setup/sequencer.js";
import { scratch } from "./probes.js";

describe("the order of test files", () => {
  it("puts the heaviest known files first and files without a time before them, keeping the given order on ties", () => {
    expect(heaviestFirst(["a", "b", "c", "d", "e"], { a: 1, b: 30, c: 1, e: 5 })).toEqual(["d", "b", "e", "a", "c"]);
  });

  it("knows every test file from the committed durations on a fresh cache, the 114 s bridge file among the heaviest", () => {
    const durations = knownDurations(scratch("durations"));
    const bridge = bridgeDurations(durations);
    expect(bridge["test_uv_coverage.py"]).toBeGreaterThan(60);
    expect(Object.keys(bridge).every((name) => /^test_\w+\.py$/.test(name))).toBe(true);
    expect(durations["test/judge/fixtures.test.ts"]).toBeGreaterThan(0);
  });
});

describe("the check's report", () => {
  const timings: Timing[] = [
    { kind: "process", stage: "test", label: 'test "a"', waitMs: 3000, workMs: 2000, endedAt: 0 },
    { kind: "process", stage: "test:bridge", label: "test_x.py", waitMs: 0, workMs: 6000, endedAt: 0 },
    { kind: "file", stage: "test", file: "test/a.test.ts", wallMs: 9000, waitMs: 3000, processes: 1, endedAt: 0 },
    { kind: "file", stage: "test:bridge", file: "bridge/tests/test_x.py", wallMs: 6000, waitMs: 0, processes: 1, endedAt: 0 },
  ];

  it("names the slowest files with their slot wait, the Blender time per stage and how busy the slots were", () => {
    expect(timingReport(timings, 5, 2)).toEqual([
      "slowest files (wall, of which waiting for a Blender slot):",
      "     9.0 s  wait    3.0 s  1 Blender  test  test/a.test.ts",
      "     6.0 s  wait    0.0 s  1 Blender  test:bridge  bridge/tests/test_x.py",
      "Blender in test:bridge: 1 processes, 6 s working, 0 s waiting for a slot",
      "Blender in test: 1 processes, 2 s working, 3 s waiting for a slot",
      "slots busy 80 % of 2 x 5 s",
    ]);
  });

  it("says a bridge timeout was spent working, with the stage, the file and the wait before it", () => {
    expect(timeoutLine("test_x.py", { seconds: 600.2, waitedSeconds: 12 }, "test:bridge")).toBe(
      "timed out working, not waiting: test_x.py in stage test:bridge worked 600.2 s, over its limit of 600 s; it waited 12.0 s for a Blender slot before it started, which does not count",
    );
  });
});

describe("check:stress options", () => {
  it("defaults to 3 runs, a quarter of the cores busy and 2 Blender render loops", () => {
    expect(defaultStress(32)).toEqual({ runs: 3, cpu: 8, blenders: 2, device: "auto", samples: 64, resolution: 640 });
  });

  it("reads every option and refuses what it does not know", () => {
    expect(parseStress(["--runs", "1", "--cpu", "0", "--blenders", "3", "--device", "cpu", "--samples", "8", "--resolution", "320"], defaultStress(8))).toEqual({ runs: 1, cpu: 0, blenders: 3, device: "cpu", samples: 8, resolution: 320 });
    expect(() => parseStress(["--runs", "0"])).toThrow(/--runs needs a whole number of at least 1/);
    expect(() => parseStress(["--fast"])).toThrow(/unknown option --fast/);
  });

  it("renders in an endless loop, on the GPU only when asked", () => {
    expect(loadScript({ device: "cpu", samples: 8, resolution: 320 })).toContain("for backend in ():");
    expect(loadScript({ device: "auto", samples: 8, resolution: 320 })).toContain('"OPTIX"');
    expect(loadScript({ device: "auto", samples: 8, resolution: 320 })).toMatch(/while True:\n {4}bpy\.ops\.render\.render\(\)$/);
  });
});
