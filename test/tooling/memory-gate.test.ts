import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { admits, cgroupHeldMb, fileNeedMb, gateBudgetMb, GATE_SHARE, knownPeaks, LARGE_FILE_MB, measuredPeaksPath, memoryLimit, rememberPeaks, unknownFileMb } from "../../scripts/lib/memory.js";
import { filePeaks, MemoryMeter, parseWindowsRows, type ProcessTable, startMemoryMeter } from "../../scripts/lib/memory-meter.js";
import { acquireSlot, slotHolders, slotsDirectory } from "../../scripts/lib/slots.js";
import { rememberDurations, topLevelRun } from "../../scripts/lib/durations.js";
import { scratch } from "./probes.js";

describe("the memory gate", () => {
  it("admits a file only while the recorded peaks of the running files and its own fit the budget", () => {
    const light = { file: "test/light.test.ts", needMb: 2000 };
    const heavy = { file: "test/heavy.test.ts", needMb: 5000 };
    expect(admits([], heavy, 6000)).toBe(true);
    expect(admits([light], heavy, 6000)).toBe(false);
    expect(admits([light], heavy, 7000)).toBe(true);
    expect(admits([light, light], { file: "test/other.test.ts", needMb: 4000 }, 6000)).toBe(true);
    expect(admits([heavy], heavy, 6000)).toBe(true);
  });

  it("also holds a new file back while the cgroup's anonymous and shared memory leave no room for it", () => {
    const light = { file: "test/light.test.ts", needMb: 500 };
    const next = { file: "test/next.test.ts", needMb: 1000 };
    expect(cgroupHeldMb(["anon 4294967296", "file 1073741824", "shmem 1073741824", ""].join("\n"))).toBe(5120);
    expect(admits([light], next, 6000, { heldMb: 5000, hardMb: 6963 })).toBe(true);
    expect(admits([light], next, 6000, { heldMb: 6500, hardMb: 6963 })).toBe(false);
    expect(admits([], next, 6000, { heldMb: 6500, hardMb: 6963 })).toBe(true);
  });

  it("treats a file without a record as large", () => {
    expect(fileNeedMb("test/new.test.ts", { "test/a.test.ts": 300 })).toBe(LARGE_FILE_MB);
    expect(fileNeedMb("test/new.test.ts", { "test/a.test.ts": 300, "test/b.test.ts": 3100 })).toBe(3100);
    expect(fileNeedMb(undefined, {})).toBe(LARGE_FILE_MB);
    expect(unknownFileMb({})).toBe(LARGE_FILE_MB);
    expect(fileNeedMb("test/a.test.ts", { "test/a.test.ts": 300 })).toBe(300);
  });

  it("takes its limit from cgroup memory.max, else physical memory, and a stated share of it", () => {
    const gb = 1024 * 1024 * 1024;
    expect(memoryLimit({ max: String(8 * gb), peak: undefined, v1Limit: undefined }, 32 * gb)).toEqual({ mb: 8192, source: "cgroup memory.max" });
    expect(memoryLimit({ max: "max", peak: undefined, v1Limit: undefined }, 32 * gb)).toEqual({ mb: 32768, source: "physical memory" });
    expect(memoryLimit({ max: undefined, peak: undefined, v1Limit: String(4 * gb) }, 32 * gb)).toEqual({ mb: 4096, source: "cgroup memory.max" });
    expect(gateBudgetMb({}, { mb: 8192, source: "cgroup memory.max" })).toBe(Math.floor(8192 * GATE_SHARE));
    expect(gateBudgetMb({ BLENDWORKS_MEMORY_BUDGET_MB: "3000" }, { mb: 8192, source: "cgroup memory.max" })).toBe(3000);
  });

  it("holds back a fake memory-heavy file while a light one runs, though slots are free, and lets no later file pass it", async () => {
    const root = scratch("memory-gate");
    const options = { root, jobs: 4, budgetMb: 6000, pollMs: 10, timeoutMs: 20_000 };
    const light = await acquireSlot({ ...options, file: "test/light.test.ts", needMb: 2000 });
    const events: string[] = [];
    const heavy = acquireSlot({ ...options, file: "test/heavy.test.ts", needMb: 5000 }).then((slot) => {
      events.push("heavy started");
      return slot;
    });
    await new Promise((done) => setTimeout(done, 200));
    const small = acquireSlot({ ...options, file: "test/small.test.ts", needMb: 1500 }).then((slot) => {
      events.push("small started");
      return slot;
    });
    await new Promise((done) => setTimeout(done, 400));
    expect(events).toEqual([]);
    expect(slotHolders(slotsDirectory(root)).map((holder) => holder.file)).toEqual(["test/light.test.ts"]);
    events.push("light ended");
    light.release();
    const started = await heavy;
    await new Promise((done) => setTimeout(done, 300));
    expect(events).toEqual(["light ended", "heavy started"]);
    expect(started.heldBackMs).toBeGreaterThan(300);
    events.push("heavy ended");
    started.release();
    (await small).release();
    expect(events).toEqual(["light ended", "heavy started", "heavy ended", "small started"]);
  });

  it("lets a second process of a running file in without counting it twice", async () => {
    const root = scratch("memory-gate-same");
    const first = await acquireSlot({ root, jobs: 2, file: "test/heavy.test.ts", needMb: 5000, budgetMb: 6000 });
    const second = await acquireSlot({ root, jobs: 2, file: "test/heavy.test.ts", needMb: 5000, budgetMb: 6000, timeoutMs: 2000 });
    expect(second.heldBackMs).toBe(0);
    first.release();
    second.release();
  });
});

describe("the memory records", () => {
  it("live next to the durations, measured values over the baseline, test files only", () => {
    const root = scratch("memory-records");
    const baseline = join(root, "baseline.json");
    writeFileSync(baseline, JSON.stringify({ "test/a.test.ts": 100, "bridge/tests/test_b.py": 200 }));
    expect(measuredPeaksPath(root)).toBe(join(root, "timings", "memory.json"));
    rememberPeaks({ "test/a.test.ts": 150.4, "unknown file in process 7": 999 }, root);
    expect(knownPeaks(root, baseline)).toEqual({ "test/a.test.ts": 150, "bridge/tests/test_b.py": 200 });
  });
});

describe("records from nested runs", () => {
  it("leave durations alone: only a file's own stage of the check updates them", () => {
    const root = scratch("nested-durations");
    const file = (name: string, stage: string) => ({ kind: "file" as const, stage, file: name, wallMs: 5000, waitMs: 1000, processes: 1, endedAt: 0 });
    const merged = rememberDurations([file("bridge/tests/test_a.py", "test:bridge"), file("bridge/tests/test_b.py", "test"), file("test/c.test.ts", "test"), file("test/d.test.ts", "test:bridge")], root);
    expect(merged).toEqual({ "bridge/tests/test_a.py": 4, "test/c.test.ts": 4 });
    expect(topLevelRun("bridge/tests/test_b.py", "test")).toBe(false);
  });
});

describe("the memory meter", () => {
  const table = (rows: [number, number, number][]): ProcessTable => new Map(rows.map(([pid, ppid, peakMb]) => [pid, { pid, ppid, peakMb, nowMb: peakMb / 2 }]));

  it("adds up the peaks of each file's processes, a worker's descendants or an attached child, for top-level runs only", () => {
    const processes = table([
      [10, 1, 300],
      [11, 10, 800],
      [12, 11, 50],
      [20, 1, 200],
      [21, 20, 1200],
      [22, 20, 700],
      [23, 22, 25],
    ]);
    const peaks = filePeaks(
      [
        { index: 0, pid: 10, file: "test/a.test.ts", needMb: 1, stage: "test", child: undefined },
        { index: 3, pid: 10, file: "bridge/tests/test_nested.py", needMb: 1, stage: "test", child: undefined },
        { index: 1, pid: 20, file: "bridge/tests/test_x.py", needMb: 1, stage: "test:bridge", child: { pid: 21, file: "bridge/tests/test_x.py", shared: false } },
        { index: 2, pid: 20, file: "bridge/tests/test_y.py", needMb: 1, stage: "test:bridge", child: { pid: 22, file: "bridge/tests/test_z.py", shared: true } },
      ],
      processes,
    );
    expect(peaks).toEqual({ "test/a.test.ts": 850, "bridge/tests/test_x.py": 1200, "bridge/tests/test_z.py": 362.5 });
  });

  it("reads the Windows sampler's rows: peak in kilobytes, current working set in bytes", () => {
    expect([...parseWindowsRows("4,0,2048,1048576;100,4,1048576,524288000;bad").values()]).toEqual([
      { pid: 4, ppid: 0, peakMb: 2, nowMb: 1 },
      { pid: 100, ppid: 4, peakMb: 1024, nowMb: 500 },
    ]);
  });

  it.skipIf(process.platform !== "linux" && process.platform !== "win32")("records the peak of a real memory-heavy child process under its file", { timeout: 60_000 }, async () => {
    const root = scratch("memory-meter");
    const directory = slotsDirectory(root);
    mkdirSync(directory, { recursive: true });
    const stage = process.env["BLENDWORKS_STAGE"];
    process.env["BLENDWORKS_STAGE"] = "test";
    const slot = await acquireSlot({ root, jobs: 1, file: "test/tooling/memory-gate.test.ts", needMb: 1, budgetMb: 100_000 });
    const child = spawn(process.execPath, ["-e", "const b = Buffer.alloc(300 * 1024 * 1024, 1); console.log('ready'); setTimeout(() => console.log(b.length), 6000);"], { stdio: ["ignore", "pipe", "ignore"] });
    const meter = startMemoryMeter(directory, 200) as MemoryMeter;
    try {
      await new Promise<void>((ready) => child.stdout.once("data", () => ready()));
      slot.attach(child.pid as number);
      const deadline = Date.now() + 30_000;
      while (meter.sampleCount() < 3 && Date.now() < deadline) await new Promise((done) => setTimeout(done, 200));
      await new Promise((done) => setTimeout(done, 1500));
    } finally {
      const peaks = meter.stop();
      child.kill();
      slot.release();
      if (stage === undefined) delete process.env["BLENDWORKS_STAGE"];
      else process.env["BLENDWORKS_STAGE"] = stage;
      expect(peaks["test/tooling/memory-gate.test.ts"]).toBeGreaterThanOrEqual(280);
    }
  });
});
