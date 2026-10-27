import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderJobs, blenderThreadArguments, blenderThreads } from "../../src/blender.js";
import { acquireSlot } from "../../scripts/lib/slots.js";
import { intervals, maxOverlap, runProbe, scratch } from "./probes.js";

async function probes(jobs: number, count: number, holdMs: number): Promise<ReturnType<typeof intervals>> {
  const root = scratch("slots");
  const log = join(root, "log.txt");
  writeFileSync(log, "");
  const runs = await Promise.all(Array.from({ length: count }, (_, index) => runProbe("slot-probe.ts", [root, String(jobs), log, `p${index}`, String(holdMs)])));
  for (const run of runs) expect(run, run.stderr).toMatchObject({ code: 0 });
  const seen = intervals(log);
  expect(seen).toHaveLength(count);
  return seen;
}

describe("the Blender process cap", { timeout: 60_000 }, () => {
  it("with BLENDWORKS_JOBS=1 never lets two processes overlap, across separate OS processes", async () => {
    const seen = await probes(1, 4, 400);
    expect(maxOverlap(seen)).toBe(1);
    const ordered = [...seen].sort((a, b) => a.start - b.start);
    for (let index = 1; index < ordered.length; index += 1) {
      expect((ordered[index] as { start: number }).start).toBeGreaterThanOrEqual((ordered[index - 1] as { end: number }).end);
    }
  });

  it("with BLENDWORKS_JOBS=2 never lets three processes overlap, across separate OS processes", async () => {
    const seen = await probes(2, 5, 500);
    expect(maxOverlap(seen)).toBeLessThanOrEqual(2);
  });

  it("with BLENDWORKS_JOBS=2 hands out exactly two slots at once", async () => {
    const root = scratch("slots-two");
    const one = await acquireSlot({ root, jobs: 2 });
    const two = await acquireSlot({ root, jobs: 2 });
    expect([one.index, two.index].sort()).toEqual([0, 1]);
    await expect(acquireSlot({ root, jobs: 2, timeoutMs: 150, pollMs: 20 })).rejects.toThrow(/timed out/);
    one.release();
    const three = await acquireSlot({ root, jobs: 2, timeoutMs: 1000 });
    expect(three.index).toBe(one.index);
    two.release();
    three.release();
  });

  it("frees a slot on release and refuses a second holder while it is taken", async () => {
    const root = scratch("slots-reuse");
    const first = await acquireSlot({ root, jobs: 1 });
    await expect(acquireSlot({ root, jobs: 1, timeoutMs: 150, pollMs: 20 })).rejects.toThrow(/timed out/);
    first.release();
    const second = await acquireSlot({ root, jobs: 1, timeoutMs: 1000 });
    expect(second.index).toBe(0);
    second.release();
  });

  it("takes over a slot whose owner process died", async () => {
    const root = scratch("slots-stale");
    const first = await acquireSlot({ root, jobs: 1 });
    first.release();
    writeFileSync(join(root, "slots", "slot-0.lock"), JSON.stringify({ pid: 2_000_000_000, token: "gone", since: 0 }));
    const slot = await acquireSlot({ root, jobs: 1, timeoutMs: 2000 });
    expect(slot.index).toBe(0);
    slot.release();
  });
});

describe("the BLENDWORKS_JOBS setting", () => {
  it("defaults to 2 and reads a whole number", () => {
    expect(blenderJobs({})).toBe(2);
    expect(blenderJobs({ BLENDWORKS_JOBS: "" })).toBe(2);
    expect(blenderJobs({ BLENDWORKS_JOBS: "5" })).toBe(5);
  });

  it("refuses zero, fractions and words", () => {
    for (const bad of ["0", "1.5", "two", "-1"]) expect(() => blenderJobs({ BLENDWORKS_JOBS: bad })).toThrow(/BLENDWORKS_JOBS/);
  });

  it("divides the processor count between the jobs, at least one thread each", () => {
    expect(blenderThreads(2, 32)).toBe(16);
    expect(blenderThreads(3, 8)).toBe(2);
    expect(blenderThreads(8, 4)).toBe(1);
    expect(blenderThreadArguments(4, 16)).toEqual(["--threads", "4"]);
  });
});
