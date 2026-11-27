import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { BlenderNotFoundError, blenderPath, resolveBlender } from "../../src/blender.js";
import { bridgeMain, BRIDGE_TESTS, runSharedBatch, SHARED_HELPER } from "../../scripts/lib/bridge-runner.js";
import { bridgeSharing, FRESH_FILES, freshReason, harnessOutcomes, parseSharedEvent, type SharedEvent, takeWork } from "../../scripts/lib/bridge-shared.js";
import { bridgePassList, comparePassLists, type PassList } from "../../scripts/lib/pass-list.js";
import { readTimingLog } from "../../scripts/lib/timings.js";
import { useBlenderSlot } from "../setup/slot.js";
import { workBudget } from "../setup/work-clock.js";
import { scratch } from "./probes.js";

useBlenderSlot();

const FIXTURES = resolve("test", "tooling", "shared-files");

function blenderAvailable(): boolean {
  try {
    resolveBlender();
    return true;
  } catch (error) {
    if (error instanceof BlenderNotFoundError) return false;
    throw error;
  }
}

function sharedRun(files: string[], env: NodeJS.ProcessEnv = {}): { events: SharedEvent[]; stdout: string } {
  const result = spawnSync(blenderPath(), ["--background", "--factory-startup", "--python", SHARED_HELPER, "--", ...files.map((file) => join(FIXTURES, file))], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024, env: { ...process.env, ...env } });
  const stdout = String(result.stdout);
  return { events: stdout.split(/\r?\n/).flatMap((line) => parseSharedEvent(line) ?? []), stdout };
}

function ends(events: SharedEvent[]): Record<string, boolean> {
  return Object.fromEntries(events.flatMap((event) => (event.event === "end" ? [[event.file, event.passed]] : [])));
}

describe("which bridge test files share a Blender", () => {
  it("shares on a host, keeps a fresh Blender per file in a container or under a CPU quota, and follows the override", () => {
    expect(bridgeSharing({}, null, false).shared).toBe(true);
    expect(bridgeSharing({}, "/.dockerenv", false).shared).toBe(false);
    expect(bridgeSharing({}, null, true).shared).toBe(false);
    expect(bridgeSharing({ BLENDWORKS_SHARED_BLENDER: "0" }, null, false).shared).toBe(false);
    expect(bridgeSharing({ BLENDWORKS_SHARED_BLENDER: "1" }, "/.dockerenv", true).shared).toBe(true);
  });

  it("lets a file opt out with a marked line, or by the runner's list, with a reason", () => {
    expect(freshReason("test_opt_out.py", FIXTURES)).toBe("leaves a persistent handler behind on purpose");
    expect(freshReason("test_fails.py", FIXTURES)).toBeUndefined();
    expect(freshReason("test_fails.py", FIXTURES, { "test_fails.py": "listed" })).toBe("listed");
    for (const [file, reason] of Object.entries(FRESH_FILES)) {
      expect(readFileSync(join(BRIDGE_TESTS, file), "utf8").length, file).toBeGreaterThan(0);
      expect(reason.length, file).toBeGreaterThan(10);
    }
  });

  it("batches shareable files up to a minute of expected work, and runs opted-out files alone", () => {
    const queue = ["slow.py", "alone.py", "a.py", "b.py", "c.py"];
    const expected = { "slow.py": 90, "alone.py": 5, "a.py": 20, "b.py": 30, "c.py": 20 };
    const shareable = (file: string) => file !== "alone.py";
    expect(takeWork(queue, shareable, expected)).toEqual({ kind: "shared", files: ["slow.py"] });
    expect(takeWork(queue, shareable, expected)).toEqual({ kind: "fresh", file: "alone.py" });
    expect(takeWork(queue, shareable, expected)).toEqual({ kind: "shared", files: ["a.py", "b.py", "c.py"] });
    expect(takeWork(queue, shareable, expected)).toBeUndefined();
  });

  it("reads the harness's per-test lines", () => {
    expect(harnessOutcomes("ok   test_a\nFAIL test_b\nnoise\n1 of 2 passed")).toEqual([
      { name: "test_a", passed: true },
      { name: "test_b", passed: false },
    ]);
  });
});

describe("a shared batch in the runner", () => {
  const fake = (stdout: string, code = 0) => async (_files: string[], options: { onStdout?: (chunk: Buffer) => void }) => {
    options.onStdout?.(Buffer.from(stdout));
    return { code, signal: null, stdout, stderr: "", seconds: 1, waitedSeconds: 0.5, timedOut: false };
  };
  const mark = (event: object) => `BLENDWORKS-SHARED ${JSON.stringify(event)}\n`;

  it("reports each file with its own output and per-test results", async () => {
    const stdout = `${mark({ event: "start", file: "a.py" })}ok   test_one\n${mark({ event: "end", file: "a.py", passed: true, seconds: 0.1, leaks: [] })}${mark({ event: "start", file: "b.py" })}FAIL test_two\n${mark({ event: "end", file: "b.py", passed: false, seconds: 0.1, leaks: [] })}`;
    const batch = await runSharedBatch(["a.py", "b.py"], fake(stdout), {});
    expect(batch.rest).toEqual([]);
    expect(batch.results.map((result) => [result.file, result.passed, result.tests])).toEqual([
      ["a.py", true, [{ name: "test_one", passed: true }]],
      ["b.py", false, [{ name: "test_two", passed: false }]],
    ]);
    expect(batch.results[1]?.output).toContain("FAIL test_two");
  });

  it("fails the file Blender ended in and hands the files after it back for a new process", async () => {
    const stdout = `${mark({ event: "start", file: "a.py" })}${mark({ event: "end", file: "a.py", passed: true, seconds: 0.1, leaks: [] })}${mark({ event: "start", file: "b.py" })}partial output\n`;
    const batch = await runSharedBatch(["a.py", "b.py", "c.py"], fake(stdout, 139), {});
    expect(batch.results.map((result) => [result.file, result.passed])).toEqual([
      ["a.py", true],
      ["b.py", false],
    ]);
    expect(batch.results[1]?.output).toContain("Blender ended during b.py");
    expect(batch.rest).toEqual(["c.py"]);
  });

  it("hands back every file after a leak, unrun", async () => {
    const stdout = `${mark({ event: "start", file: "a.py" })}${mark({ event: "end", file: "a.py", passed: false, seconds: 0.1, leaks: ["handlers.x: added ['f']"] })}`;
    const batch = await runSharedBatch(["a.py", "b.py", "c.py"], fake(stdout), {});
    expect(batch.results.map((result) => [result.file, result.passed])).toEqual([["a.py", false]]);
    expect(batch.rest).toEqual(["b.py", "c.py"]);
  });
});

describe.skipIf(!blenderAvailable())("files sharing one Blender", workBudget(240_000), () => {
  it("start from factory state after a file changed data, scene, environment and modules, and keep failures to their file", () => {
    const run = sharedRun(["test_clean_a.py", "test_check_fresh.py", "test_fails.py", "test_check_fresh.py", "test_clean_a.py", "test_check_fresh.py"]);
    expect(run.events.filter((event) => event.event === "end").map((event) => [event.file, event.event === "end" && event.passed])).toEqual([
      ["test_clean_a.py", true],
      ["test_check_fresh.py", true],
      ["test_fails.py", false],
      ["test_check_fresh.py", true],
      ["test_clean_a.py", true],
      ["test_check_fresh.py", true],
    ]);
  });

  it("catch a deliberate state leak, fail the leaking file and run nothing after it in that process", () => {
    const handler = sharedRun(["test_check_fresh.py", "test_leak_handler.py", "test_after_leak.py"]);
    expect(ends(handler.events)).toEqual({ "test_check_fresh.py": true, "test_leak_handler.py": false });
    const leak = handler.events.find((event) => event.event === "end" && event.file === "test_leak_handler.py");
    expect(leak?.event === "end" ? leak.leaks.join("\n") : "").toMatch(/handlers\.depsgraph_update_post: added \[.*shared_probe_handler/);
    const registered = sharedRun(["test_leak_class.py", "test_after_leak.py"]);
    expect(ends(registered.events)).toEqual({ "test_leak_class.py": false });
    expect(registered.stdout).toMatch(/leaked state: classes: added \[.*SHARED_PROBE_PG_leak/);
  });

  it("stop a process that holds more memory than the recycle limit after a reset, so the next files get a new one", () => {
    const run = sharedRun(["test_clean_a.py", "test_check_fresh.py"], { BLENDWORKS_SHARED_RECYCLE_MB: "1" });
    expect(ends(run.events)).toEqual({ "test_clean_a.py": true });
    expect(run.stdout).toMatch(/more than 1 MB; the files after it run in a new process/);
  });

  const passList = async (env: NodeJS.ProcessEnv, filters: string[]): Promise<{ code: number; list: PassList }> => {
    const log = join(scratch("pass-list"), "timings.jsonl");
    const code = await bridgeMain(filters, { ...process.env, BLENDWORKS_TIMINGS: log, BLENDWORKS_STAGE: "test:bridge", ...env });
    return { code, list: bridgePassList(readTimingLog(log)) };
  };

  it("give the same per-file and per-test pass list at jobs 2 and 4, shared and fresh, with a failing file among them", async () => {
    const fixtures = { BLENDWORKS_BRIDGE_TESTS: FIXTURES };
    const files = ["test_clean_a", "test_check_fresh", "test_fails", "test_opt_out", "test_after_leak"];
    const two = await passList({ ...fixtures, BLENDWORKS_JOBS: "2", BLENDWORKS_SHARED_BLENDER: "1" }, files);
    const four = await passList({ ...fixtures, BLENDWORKS_JOBS: "4", BLENDWORKS_SHARED_BLENDER: "1" }, files);
    const fresh = await passList({ ...fixtures, BLENDWORKS_JOBS: "2", BLENDWORKS_SHARED_BLENDER: "0" }, files);
    expect(two.code).toBe(1);
    expect(Object.keys(two.list.files)).toHaveLength(5);
    expect(two.list.files["test/tooling/shared-files/test_fails.py"]).toBe("failed");
    expect(two.list.tests["test/tooling/shared-files/test_fails.py > test_passes"]).toBe("passed");
    expect(comparePassLists(two.list, four.list)).toEqual([]);
    expect(comparePassLists(two.list, fresh.list)).toEqual([]);
  });

  it("give the same pass list for real bridge test files at jobs 2 and 4, shared and fresh", async () => {
    const files = ["test_smoke", "test_materials", "test_chip", "test_scene_info", "test_fracture", "test_bake.py"];
    const two = await passList({ BLENDWORKS_JOBS: "2", BLENDWORKS_SHARED_BLENDER: "1" }, files);
    const four = await passList({ BLENDWORKS_JOBS: "4", BLENDWORKS_SHARED_BLENDER: "1" }, files);
    const fresh = await passList({ BLENDWORKS_JOBS: "2", BLENDWORKS_SHARED_BLENDER: "0" }, files);
    expect(two.code).toBe(0);
    expect(Object.keys(two.list.files).length).toBeGreaterThanOrEqual(6);
    expect(Object.keys(two.list.tests).length).toBeGreaterThan(20);
    expect(comparePassLists(two.list, four.list)).toEqual([]);
    expect(comparePassLists(two.list, fresh.list)).toEqual([]);
  });
});
