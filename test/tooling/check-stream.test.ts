import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { runBridgeFile } from "../../scripts/lib/bridge-runner.js";
import { fullPhases } from "../../scripts/lib/checks.js";
import { DEFAULT_FILE_LIMIT_S, DEFAULT_HEARTBEAT_S, EXEMPT_FILES, fileLimitMs, heartbeatMs } from "../../scripts/lib/file-limits.js";
import { npmStep, runPhases, type Step } from "../../scripts/lib/pipeline.js";
import { waitStarted } from "../../scripts/lib/locks.js";
import { announceFile, LineSplitter, PROGRESS_MARK, PROGRESS_VARIABLE, Progress, WaitLog } from "../../scripts/lib/progress.js";
import { repoRoot } from "../../scripts/lib/paths.js";
import { TIMINGS_VARIABLE } from "../../scripts/lib/timings.js";
import ProgressReporter from "../setup/progress-reporter.js";
import { waitFor } from "../setup/wait-for.js";
import { scratch } from "./probes.js";

function mark(event: object): string {
  return `${PROGRESS_MARK}${JSON.stringify(event)}`;
}

function node(name: string, source: string): Step {
  return { name, command: process.execPath, args: ["-e", source] };
}

function waitForBarrier(barrier: string): string {
  return `
    const fs = require("node:fs");
    const wait = setInterval(() => { if (fs.existsSync(${JSON.stringify(barrier)})) clearInterval(wait); }, 10);
  `;
}

function fakeProgress(limitMs = 100_000, exempt: Record<string, string> = {}) {
  const clock = { now: 0 };
  const lines: string[] = [];
  const progress = new Progress({ now: () => clock.now, print: (line) => lines.push(line), limitMs, exempt });
  return { clock, lines, progress };
}

const PASSED = { code: 0, signal: null, stdout: "", stderr: "", seconds: 2, waitedSeconds: 0, timedOut: false };

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("streaming progress", () => {
  it("prints a line with phase, file, result and time as each file ends, in the order they end", () => {
    const { clock, lines, progress } = fakeProgress();
    progress.stepStarted("test");
    progress.event("test", { event: "start", file: "test/a.test.ts" });
    progress.event("test", { event: "start", file: "test/b.test.ts" });
    clock.now = 3_000;
    progress.event("test", { event: "end", file: "test/b.test.ts", passed: true, seconds: 2.5 });
    expect(lines).toEqual(["ok   [test] test/b.test.ts 2.5 s"]);
    clock.now = 7_000;
    progress.event("test", { event: "end", file: "test/a.test.ts", passed: false });
    expect(lines).toEqual(["ok   [test] test/b.test.ts 2.5 s", "FAIL [test] test/a.test.ts 7.0 s"]);
  });

  it("reaches the printer while the step still runs, as one whole line, and keeps the marker out of the step output", async () => {
    const folder = scratch("stream-lines");
    const barrier = join(folder, "release");
    const end = `${mark({ event: "end", file: "test/a.test.ts", passed: true, seconds: 1 })}\n`;
    const source = `
      process.stdout.write(${JSON.stringify(mark({ event: "start", file: "test/a.test.ts" }))} + "\\n");
      process.stdout.write(${JSON.stringify(end.slice(0, 20))});
      setTimeout(() => {
        process.stdout.write(${JSON.stringify(end.slice(20))});
        process.stdout.write("plain output\\n");
      }, 50);
      ${waitForBarrier(barrier)}
    `;
    const printed: string[] = [];
    const run = runPhases([[node("s", source)]], {
      print: (line) => {
        printed.push(line);
        writeFileSync(barrier, "x");
      },
      heartbeatMs: 3_600_000,
    });
    await waitFor(() => existsSync(barrier), { description: "the first progress line" });
    const result = await run;
    expect(printed).toEqual(["ok   [s] test/a.test.ts 1.0 s"]);
    expect(result.results[0]?.output).toBe("plain output\n");
  });

  it("splits chunks into whole lines and keeps the unfinished tail", () => {
    const splitter = new LineSplitter();
    expect(splitter.push("one\ntw")).toEqual(["one"]);
    expect(splitter.push("o\r\nthree")).toEqual(["two"]);
    expect(splitter.rest()).toBe("three");
  });

  it("keeps the marker variable out of the test workers, whose own output must not read as progress", () => {
    expect(process.env[PROGRESS_VARIABLE]).toBeUndefined();
  });

  it("announces files only when the check asks for it", () => {
    const written: string[] = [];
    announceFile({ event: "start", file: "x" }, {}, (line) => written.push(line));
    expect(written).toEqual([]);
    announceFile({ event: "start", file: "x" }, { [PROGRESS_VARIABLE]: "1" }, (line) => written.push(line));
    expect(written).toEqual([mark({ event: "start", file: "x" })]);
  });

  it("makes the vitest reporter announce each test file", () => {
    const lines: string[] = [];
    vi.stubEnv(PROGRESS_VARIABLE, "1");
    vi.spyOn(console, "log").mockImplementation((line: string) => void lines.push(line));
    const reporter = new ProgressReporter();
    const module = { relativeModuleId: "test/a.test.ts", state: () => "failed", diagnostic: () => ({ duration: 1500 }) };
    reporter.onTestModuleStart(module as never);
    reporter.onTestModuleEnd(module as never);
    expect(lines).toEqual([mark({ event: "start", file: "test/a.test.ts", limited: true }), mark({ event: "end", file: "test/a.test.ts", passed: false, seconds: 1.5 })]);
  });

  it("makes the bridge runner announce each file from the moment it has a Blender slot", async () => {
    const lines: string[] = [];
    vi.stubEnv(PROGRESS_VARIABLE, "1");
    vi.spyOn(console, "log").mockImplementation((line: string) => void lines.push(line));
    const events: string[] = [];
    await runBridgeFile("test_x.py", async (_file, options) => {
      events.push(`queued ${lines.length}`);
      options.onStart?.();
      events.push(`started ${lines.length}`);
      return PASSED;
    });
    expect(events).toEqual(["queued 0", "started 1"]);
    expect(lines.filter((line) => line.startsWith(PROGRESS_MARK))).toEqual([mark({ event: "start", file: "bridge/tests/test_x.py" }), mark({ event: "end", file: "bridge/tests/test_x.py", passed: true, seconds: 2 })]);
  });

  it("gives the full check's test step the progress reporter and no other step", () => {
    const steps = Object.fromEntries((fullPhases()[0] ?? []).map((step) => [step.name, step.args.join(" ")]));
    expect(steps["test"]).toContain("--reporter=./test/setup/progress-reporter.ts");
    expect(steps["rules"]).not.toContain("--reporter");
    expect(existsSync(join(repoRoot, "test/setup/progress-reporter.ts"))).toBe(true);
    expect(npmStep("test", ["a.test.ts"], {}, ["--reporter=x"]).name).toBe("test a.test.ts");
  });
});

describe("the heartbeat", () => {
  it("names the files still running and drops the ones that ended", () => {
    const { clock, lines, progress } = fakeProgress();
    progress.stepStarted("test");
    progress.stepStarted("rules");
    progress.event("test", { event: "start", file: "test/a.test.ts" });
    progress.event("test", { event: "start", file: "test/b.test.ts" });
    clock.now = 65_000;
    progress.event("test", { event: "end", file: "test/b.test.ts", passed: true, seconds: 1 });
    lines.length = 0;
    progress.heartbeat();
    expect(lines).toEqual(["still running 1:05: test (1 done; running test/a.test.ts 65 s), rules"]);
  });

  it("repeats on its interval while a step is quiet, naming its running file", async () => {
    const folder = scratch("heartbeat");
    const barrier = join(folder, "release");
    const source = `
      console.log(${JSON.stringify(mark({ event: "start", file: "test/quiet.test.ts" }))});
      ${waitForBarrier(barrier)}
    `;
    const beats: string[] = [];
    const result = await runPhases([[node("quiet", source)]], {
      heartbeatMs: 20,
      print: (line) => {
        if (line.startsWith("still running") && line.includes("quiet (running test/quiet.test.ts")) beats.push(line);
        if (beats.length >= 3) writeFileSync(barrier, "x");
      },
    });
    expect(result.passed).toBe(true);
    expect(beats.length).toBeGreaterThanOrEqual(3);
  });

  it("defaults far below the quiet limit of the judge, and reads its override", () => {
    expect(DEFAULT_HEARTBEAT_S).toBeLessThan(900);
    expect(heartbeatMs({})).toBe(DEFAULT_HEARTBEAT_S * 1000);
    expect(heartbeatMs({ BLENDWORKS_HEARTBEAT_S: "5" })).toBe(5000);
    expect(heartbeatMs({ BLENDWORKS_HEARTBEAT_S: "nonsense" })).toBe(DEFAULT_HEARTBEAT_S * 1000);
  });
});

describe("the per-file limit", () => {
  it("names a file only after it runs past the limit", () => {
    const { clock, progress } = fakeProgress(100_000);
    progress.stepStarted("test");
    progress.event("test", { event: "start", file: "test/slow.test.ts", limited: true });
    clock.now = 100_000;
    expect(progress.overdue()).toEqual([]);
    clock.now = 100_001;
    expect(progress.overdue()).toEqual([{ step: "test", file: "test/slow.test.ts", seconds: 100.001 }]);
    progress.event("test", { event: "end", file: "test/slow.test.ts", passed: true });
    expect(progress.overdue()).toEqual([]);
  });

  it("does not apply to a file listed with a reason", () => {
    const { clock, progress } = fakeProgress(1000, { "test/long.test.ts": "renders for minutes by design" });
    progress.stepStarted("test");
    progress.event("test", { event: "start", file: "test/long.test.ts", limited: true });
    progress.event("test", { event: "start", file: "test/other.test.ts", limited: true });
    clock.now = 5000;
    expect(progress.overdue().map((late) => late.file)).toEqual(["test/other.test.ts"]);
  });

  it("does not count the time a file waits for a Blender slot, ended or still going on", () => {
    const { clock, progress } = fakeProgress(100_000);
    progress.stepStarted("test");
    progress.event("test", { event: "start", file: "test/queued.test.ts", limited: true });
    progress.waiting({ kind: "wait", file: "test/queued.test.ts", state: "begin" });
    clock.now = 400_000;
    expect(progress.overdue()).toEqual([]);
    progress.waiting({ kind: "wait", file: "test/queued.test.ts", state: "end", waitedMs: 400_000 });
    clock.now = 450_000;
    expect(progress.overdue()).toEqual([]);
    clock.now = 500_001;
    expect(progress.overdue().map((late) => [late.file, late.seconds])).toEqual([["test/queued.test.ts", 100.001]]);
  });

  it("reads the waits other processes append to the timing log, whole lines only", () => {
    const log = join(scratch("wait-log"), "timings.jsonl");
    const reader = new WaitLog(log);
    expect(reader.poll()).toEqual([]);
    const begin = JSON.stringify({ kind: "wait", file: "a", state: "begin" });
    writeFileSync(log, `${JSON.stringify({ kind: "file", file: "a" })}
${begin}
{"kind":"wa`);
    expect(reader.poll()).toEqual([{ kind: "wait", file: "a", state: "begin" }]);
    appendFileSync(log, `it","file":"b","state":"end","waitedMs":5}
`);
    expect(reader.poll()).toEqual([{ kind: "wait", file: "b", state: "end", waitedMs: 5 }]);
    expect(reader.poll()).toEqual([]);
  });

  it("leaves a file that waits for a slot running, while the check watches it", async () => {
    const folder = scratch("waiting-file");
    const barrier = join(folder, "release");
    const log = join(folder, "timings.jsonl");
    const source = `
      console.log(${JSON.stringify(mark({ event: "start", file: "test/queued.test.ts", limited: true }))});
      require("node:fs").appendFileSync(${JSON.stringify(log)}, ${JSON.stringify(JSON.stringify({ kind: "wait", file: "test/queued.test.ts", state: "begin" }))} + "\\n");
      ${waitForBarrier(barrier)}
    `;
    let beats = 0;
    const result = await runPhases([[node("test", source)]], {
      limitMs: 100,
      checkMs: 5,
      heartbeatMs: 20,
      waitLog: log,
      print: (line) => {
        if (line.startsWith("still running")) beats += 1;
        if (beats >= 20) writeFileSync(barrier, "x");
      },
    });
    expect(result.passed).toBe(true);
  });

  it("makes the test workers report their waits for a slot to the timing log", () => {
    const log = join(scratch("worker-waits"), "timings.jsonl");
    vi.stubEnv(TIMINGS_VARIABLE, log);
    waitStarted()();
    const records = readFileSync(log, "utf8").trim().split("\n").map((line) => JSON.parse(line) as { state: string; file: string; waitedMs?: number });
    expect(records.map((record) => record.state)).toEqual(["begin", "end"]);
    expect(records[0]?.file).toBe("test/tooling/check-stream.test.ts");
    expect(typeof records[1]?.waitedMs).toBe("number");
  });

  it("stops a hung file, fails its step and names the file", async () => {
    const source = `
      console.log(${JSON.stringify(mark({ event: "start", file: "test/hung.test.ts", limited: true }))});
      setInterval(() => {}, 1000);
    `;
    const result = await runPhases([[node("test", source)]], { limitMs: 1, checkMs: 10, heartbeatMs: 3_600_000, print: () => undefined });
    expect(result.passed).toBe(false);
    expect(result.results[0]?.cancelled).toBeUndefined();
    expect(result.results[0]?.output).toContain("FAIL test/hung.test.ts worked");
    expect(result.results[0]?.output).toContain("past its limit of 0.001 s per test file");
  });

  it("leaves an exempt file running", async () => {
    const folder = scratch("exempt");
    const barrier = join(folder, "release");
    const source = `
      console.log(${JSON.stringify(mark({ event: "start", file: "test/long.test.ts", limited: true }))});
      ${waitForBarrier(barrier)}
    `;
    let beats = 0;
    const result = await runPhases([[node("test", source)]], {
      limitMs: 1,
      checkMs: 5,
      heartbeatMs: 20,
      exempt: { "test/long.test.ts": "long on purpose" },
      print: (line) => {
        if (line.startsWith("still running")) beats += 1;
        if (beats >= 4) writeFileSync(barrier, "x");
      },
    });
    expect(result.passed).toBe(true);
  });

  it("is documented, configurable, well under the quiet limit, and every exemption has a reason", () => {
    expect(DEFAULT_FILE_LIMIT_S).toBeLessThan(900);
    expect(fileLimitMs({})).toBe(DEFAULT_FILE_LIMIT_S * 1000);
    expect(fileLimitMs({ BLENDWORKS_FILE_LIMIT_S: "30" })).toBe(30_000);
    for (const [file, reason] of Object.entries(EXEMPT_FILES)) {
      expect(existsSync(join(repoRoot, file)), file).toBe(true);
      expect(reason.trim().length, file).toBeGreaterThan(10);
    }
  });

  it("hands the bridge process the configured limit", async () => {
    const seen: (number | undefined)[] = [];
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    await runBridgeFile(
      "test_x.py",
      async (_file, options) => {
        seen.push(options.timeoutMs);
        return PASSED;
      },
      { BLENDWORKS_FILE_LIMIT_S: "42" },
    );
    expect(seen).toEqual([42_000]);
  });
});
