import { mkdirSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { blenderJobs } from "../../src/blender.js";
import { type FileLock, readOwner, processAlive, tryLock } from "./locks.js";
import { cacheRoot, ensureCacheRoot } from "./paths.js";

export type SlotOptions = { root?: string; jobs?: number; timeoutMs?: number; pollMs?: number };

export type Slot = { index: number; release(): void };

export function slotsDirectory(root: string): string {
  return join(root, "slots");
}

const SLEEP_CELL = new Int32Array(new SharedArrayBuffer(4));

function prepare(options: SlotOptions): { directory: string; jobs: number; deadline: number; pollMs: number } {
  const root = ensureCacheRoot(options.root ?? cacheRoot());
  const directory = slotsDirectory(root);
  mkdirSync(directory, { recursive: true });
  return { directory, jobs: options.jobs ?? blenderJobs(), deadline: Date.now() + (options.timeoutMs ?? 30 * 60_000), pollMs: options.pollMs ?? 40 };
}

function takeFree(directory: string, jobs: number): Slot | undefined {
  for (let index = 0; index < jobs; index += 1) {
    const lock: FileLock | undefined = tryLock(join(directory, `slot-${index}.lock`));
    if (lock !== undefined) return { index, release: () => lock.release() };
  }
  return undefined;
}

function timeout(jobs: number, directory: string): Error {
  return new Error(`timed out waiting for one of ${jobs} Blender slots in ${directory}`);
}

export async function acquireSlot(options: SlotOptions = {}): Promise<Slot> {
  const { directory, jobs, deadline, pollMs } = prepare(options);
  for (;;) {
    const slot = takeFree(directory, jobs);
    if (slot !== undefined) return slot;
    if (Date.now() > deadline) throw timeout(jobs, directory);
    await sleep(pollMs);
  }
}

export function acquireSlotSync(options: SlotOptions = {}): Slot {
  const { directory, jobs, deadline, pollMs } = prepare(options);
  for (;;) {
    const slot = takeFree(directory, jobs);
    if (slot !== undefined) return slot;
    if (Date.now() > deadline) throw timeout(jobs, directory);
    Atomics.wait(SLEEP_CELL, 0, 0, pollMs);
  }
}

export async function withSlot<T>(task: (slot: Slot) => Promise<T>, options: SlotOptions = {}): Promise<T> {
  const slot = await acquireSlot(options);
  try {
    return await task(slot);
  } finally {
    slot.release();
  }
}

export function withSlotSync<T>(task: (slot: Slot) => T, options: SlotOptions = {}): T {
  const slot = acquireSlotSync(options);
  try {
    return task(slot);
  } finally {
    slot.release();
  }
}

export function activeSlots(root: string = cacheRoot()): { index: number; pid: number }[] {
  let names: string[];
  try {
    names = readdirSync(slotsDirectory(root));
  } catch {
    return [];
  }
  const out: { index: number; pid: number }[] = [];
  for (const name of names) {
    const match = /^slot-(\d+)\.lock$/.exec(name);
    if (match === null) continue;
    const owner = readOwner(join(slotsDirectory(root), name));
    if (owner !== undefined && owner !== "unreadable" && processAlive(owner.pid)) out.push({ index: Number(match[1]), pid: owner.pid });
  }
  return out.sort((a, b) => a.index - b.index);
}

