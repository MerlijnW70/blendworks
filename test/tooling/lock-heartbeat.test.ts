import { existsSync, mkdirSync, utimesSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { describe, expect, it } from "vitest";
import { fresh, holderAlive, tryLock } from "../../scripts/lib/locks.js";
import { acquireSlot, queueDirectory, SlotWaitTimeout, slotAttempts, slotsDirectory } from "../../scripts/lib/slots.js";
import { backoff } from "../../scripts/lib/slot-wait.js";
import { waitFor } from "../setup/wait-for.js";
import { scratch } from "./probes.js";

const MINUTE_MS = 60_000;

function ownedByLiveProcess(path: string, silentForMs: number): void {
  writeFileSync(path, JSON.stringify({ pid: process.pid, token: "left-by-a-dead-holder", since: Date.now() - silentForMs }));
  const then = new Date(Date.now() - silentForMs);
  utimesSync(path, then, then);
}

describe("a lock whose holder died is reclaimed even when its pid belongs to a live process again", () => {
  it("a file lock that shows a live pid but no sign of life for minutes is taken over", () => {
    const path = join(scratch("pid-reuse"), "x.lock");
    ownedByLiveProcess(path, 5 * MINUTE_MS);
    expect(holderAlive(path)).toBe(false);
    expect(tryLock(path)).toBeUndefined();
    const taken = tryLock(path);
    expect(taken).toBeDefined();
    taken?.release();
  });

  it("a file lock that shows a live pid and was written a moment ago is not taken", () => {
    const path = join(scratch("live-holder"), "x.lock");
    ownedByLiveProcess(path, 0);
    expect(holderAlive(path)).toBe(true);
    expect(tryLock(path)).toBeUndefined();
    expect(tryLock(path)).toBeUndefined();
    expect(existsSync(path)).toBe(true);
  });

  it("a lock this process holds keeps showing signs of life", async () => {
    const path = join(scratch("beat"), "x.lock");
    const lock = tryLock(path);
    expect(lock).toBeDefined();
    const then = new Date(Date.now() - 5 * MINUTE_MS);
    utimesSync(path, then, then);
    expect(fresh(path)).toBe(false);
    await waitFor(() => fresh(path), { description: "the heartbeat to refresh the lock", timeoutMs: 30_000 });
    expect(holderAlive(path)).toBe(true);
    lock?.release();
  });

  it("a Blender slot left by a dead holder with a reused pid is given to the next waiter", async () => {
    const root = scratch("slot-reuse");
    const directory = slotsDirectory(root);
    mkdirSync(directory, { recursive: true });
    ownedByLiveProcess(join(directory, "slot-0.lock"), 5 * MINUTE_MS);
    const slot = await acquireSlot({ root, jobs: 1, pollMs: 5, timeoutMs: 20_000 });
    expect(slot.index).toBe(0);
    slot.release();
  });

  it("a Blender slot held by a live holder is not given away", async () => {
    const root = scratch("slot-live");
    const directory = slotsDirectory(root);
    mkdirSync(directory, { recursive: true });
    ownedByLiveProcess(join(directory, "slot-0.lock"), 0);
    await expect(acquireSlot({ root, jobs: 1, pollMs: 5, timeoutMs: 300 })).rejects.toBeInstanceOf(SlotWaitTimeout);
  });

  it("a queue ticket of a live pid that stopped showing signs of life does not hold up the queue", async () => {
    const root = scratch("ticket-reuse");
    const queue = queueDirectory(slotsDirectory(root));
    mkdirSync(queue, { recursive: true });
    const ticket = join(queue, `000000000000001-000001-${process.pid}-abcdef12.ticket`);
    writeFileSync(ticket, "");
    const then = new Date(Date.now() - 5 * MINUTE_MS);
    utimesSync(ticket, then, then);
    const slot = await acquireSlot({ root, jobs: 1, pollMs: 5, timeoutMs: 20_000 });
    slot.release();
    expect(existsSync(ticket)).toBe(false);
  });
});

describe("waiting for a Blender slot", () => {
  it("backs off between polls: the delays grow from the first to a ceiling", () => {
    const delays = backoff(40, 500);
    const seen = Array.from({ length: 25 }, () => delays.next());
    expect(seen[0]).toBe(40);
    for (let index = 1; index < seen.length; index += 1) expect(seen[index]).toBeGreaterThanOrEqual(seen[index - 1] as number);
    expect(Math.max(...seen)).toBe(400);
    expect(seen.reduce((sum, delay) => sum + delay, 0)).toBeGreaterThan(5_000);
  });

  it("reads the slot files far less often than every 40 ms while it waits", async () => {
    const root = scratch("backoff");
    const held = await acquireSlot({ root, jobs: 1 });
    const before = slotAttempts();
    const waiting = acquireSlot({ root, jobs: 1, pollMs: 40 });
    await sleep(1_200);
    const polls = slotAttempts() - before;
    held.release();
    (await waiting).release();
    expect(polls).toBeLessThan(15);
  });

  it("wakes when a slot is released, however far the polling has backed off", { timeout: 30_000 }, async () => {
    const root = scratch("wake");
    const held = await acquireSlot({ root, jobs: 1 });
    const waiting = acquireSlot({ root, jobs: 1, pollMs: 60_000, timeoutMs: 120_000 });
    await waitFor(() => existsSync(queueDirectory(slotsDirectory(root))), { description: "the queue" });
    held.release();
    (await waiting).release();
  });
});
