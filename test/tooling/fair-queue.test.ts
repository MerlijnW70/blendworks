import { readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { acquireSlot, acquireSlotSync, queueDirectory, slotsDirectory } from "../../scripts/lib/slots.js";
import { intervals, runProbe, scratch } from "./probes.js";

describe("Blender slots go to waiters in the order they asked", { timeout: 60_000 }, () => {
  it("a process that releases and asks again at once queues behind one that was already waiting", async () => {
    const root = scratch("fair");
    const log = join(root, "log.txt");
    writeFileSync(log, "");
    const runs = await Promise.all([runProbe("queue-probe.ts", [root, "1", log, "greedy", "400", "3", "0"]), runProbe("queue-probe.ts", [root, "1", log, "patient", "100", "1", "200"])]);
    for (const run of runs) expect(run, run.stderr).toMatchObject({ code: 0 });
    const order = intervals(log)
      .sort((a, b) => a.start - b.start)
      .map((item) => item.label);
    expect(order).toEqual(["greedy1", "patient1", "greedy2", "greedy3"]);
  });

  it("three waiters in one process get the slot first come, first served", async () => {
    const root = scratch("fair-local");
    const held = await acquireSlot({ root, jobs: 1 });
    const order: string[] = [];
    const waiters = ["a", "b", "c"].map((name) => acquireSlot({ root, jobs: 1, pollMs: 5 }).then((slot) => {
      order.push(name);
      setTimeout(() => slot.release(), 30);
    }));
    await new Promise((done) => setTimeout(done, 100));
    held.release();
    await Promise.all(waiters);
    expect(order).toEqual(["a", "b", "c"]);
    expect(readdirSync(queueDirectory(slotsDirectory(root)))).toEqual([]);
  });

  it("skips the tickets of dead processes and of its own process while it blocks", async () => {
    const root = scratch("fair-stale");
    const queue = queueDirectory(slotsDirectory(root));
    const first = await acquireSlot({ root, jobs: 1 });
    first.release();
    writeFileSync(join(queue, `000000000000001-000001-2000000000-abcdef12.ticket`), "");
    const stale = await acquireSlot({ root, jobs: 1, timeoutMs: 2000 });
    stale.release();
    expect(readdirSync(queue)).toEqual([]);
    const held = await acquireSlot({ root, jobs: 1 });
    const pending = acquireSlot({ root, jobs: 1, pollMs: 5, timeoutMs: 5000 });
    await new Promise((done) => setTimeout(done, 20));
    held.release();
    const blocking = acquireSlotSync({ root, jobs: 1, pollMs: 5, timeoutMs: 2000 });
    blocking.release();
    (await pending).release();
  });
});
