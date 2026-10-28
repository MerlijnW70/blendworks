import { randomUUID } from "node:crypto";
import { mkdirSync, readdirSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { blenderJobs } from "../../src/blender.js";
import { trackHeartbeat, untrackHeartbeat } from "./heartbeat.js";
import { type FileLock, fresh, holderAlive, readOwner, processAlive, tryLock, waitStarted } from "./locks.js";
import { cacheRoot, ensureCacheRoot } from "./paths.js";
import { asyncBackoff, syncBackoff, watchChanges } from "./slot-wait.js";
import { currentStage, recordTiming } from "./timings.js";

export type SlotOptions = { root?: string; jobs?: number; timeoutMs?: number; pollMs?: number; label?: string };

export type Slot = { index: number; waitedMs: number; release(): void };

const acquisitionObservers = new Set<() => void>();
let labeler: () => string | undefined = () => undefined;

let attempts = 0;

export function slotAttempts(): number {
  return attempts;
}

export function observeAcquisitions(observer: () => void): () => void {
  acquisitionObservers.add(observer);
  return () => acquisitionObservers.delete(observer);
}

export function labelSlotsWith(next: () => string | undefined): void {
  labeler = next;
}

export class SlotWaitTimeout extends Error {
  constructor(
    readonly jobs: number,
    readonly directory: string,
    readonly waitedMs: number,
    readonly label: string,
  ) {
    super(`timed out waiting, not working: ${label} waited ${(waitedMs / 1000).toFixed(1)} s for one of ${jobs} Blender slots in ${directory} (stage ${currentStage()})`);
  }
}

export function slotsDirectory(root: string): string {
  return join(root, "slots");
}

const SLEEP_CELL = new Int32Array(new SharedArrayBuffer(4));

type Request = { directory: string; jobs: number; started: number; deadline: number; pollMs: number; label: string; ticket: string };

const TICKET = /^(\d{15})-(\d{6})-(\d+)-[0-9a-f]{8}\.ticket$/;
let ticketSequence = 0;

export function queueDirectory(directory: string): string {
  return join(directory, "queue");
}

function joinQueue(directory: string): string {
  const queue = queueDirectory(directory);
  mkdirSync(queue, { recursive: true });
  ticketSequence = (ticketSequence + 1) % 1_000_000;
  const ticket = `${String(Date.now()).padStart(15, "0")}-${String(ticketSequence).padStart(6, "0")}-${process.pid}-${randomUUID().slice(0, 8)}.ticket`;
  writeFileSync(join(queue, ticket), "", { flag: "wx" });
  trackHeartbeat(join(queue, ticket));
  return ticket;
}

function removeQuietly(path: string): void {
  try {
    unlinkSync(path);
  } catch {
    return;
  }
}

function leaveQueue(request: Request): void {
  untrackHeartbeat(join(queueDirectory(request.directory), request.ticket));
  removeQuietly(join(queueDirectory(request.directory), request.ticket));
}

function placeInQueue(request: Request, blocking: boolean): number {
  const queue = queueDirectory(request.directory);
  let names: string[];
  try {
    names = readdirSync(queue);
  } catch {
    return 0;
  }
  let ahead = 0;
  for (const name of names) {
    const match = TICKET.exec(name);
    if (match === null || name >= request.ticket) continue;
    const pid = Number(match[3]);
    if (blocking && pid === process.pid) continue;
    if (processAlive(pid) && fresh(join(queue, name))) ahead += 1;
    else removeQuietly(join(queue, name));
  }
  return ahead;
}

function busySlots(request: Request): number {
  let busy = 0;
  for (let index = 0; index < request.jobs; index += 1) {
    if (holderAlive(join(request.directory, `slot-${index}.lock`))) busy += 1;
  }
  return busy;
}

function myTurn(request: Request, blocking: boolean): boolean {
  return placeInQueue(request, blocking) < Math.max(1, request.jobs - busySlots(request));
}

function prepare(options: SlotOptions): Request {
  const root = ensureCacheRoot(options.root ?? cacheRoot());
  const directory = slotsDirectory(root);
  mkdirSync(directory, { recursive: true });
  const started = performance.now();
  const label = options.label ?? labeler() ?? `process ${process.pid}`;
  return { directory, jobs: options.jobs ?? blenderJobs(), started, deadline: started + (options.timeoutMs ?? 30 * 60_000), pollMs: options.pollMs ?? 40, label, ticket: joinQueue(directory) };
}

function attempt(request: Request, blocking = false): Slot | undefined {
  attempts += 1;
  return myTurn(request, blocking) ? takeFree(request) : undefined;
}

function takeFree(request: Request): Slot | undefined {
  for (let index = 0; index < request.jobs; index += 1) {
    const lock: FileLock | undefined = tryLock(join(request.directory, `slot-${index}.lock`));
    if (lock === undefined) continue;
    const acquired = performance.now();
    const waitedMs = acquired - request.started;
    const stage = currentStage();
    for (const observer of acquisitionObservers) observer();
    return {
      index,
      waitedMs,
      release: () => {
        if (!lock.release()) return;
        recordTiming({ kind: "process", stage, label: request.label, waitMs: Math.round(waitedMs), workMs: Math.round(performance.now() - acquired), endedAt: Date.now() });
      },
    };
  }
  return undefined;
}

function expired(request: Request): SlotWaitTimeout | undefined {
  const now = performance.now();
  return now > request.deadline ? new SlotWaitTimeout(request.jobs, request.directory, now - request.started, request.label) : undefined;
}

export async function acquireSlot(options: SlotOptions = {}): Promise<Slot> {
  const request = prepare(options);
  try {
    const immediate = attempt(request);
    if (immediate !== undefined) return immediate;
    const done = waitStarted();
    const changes = watchChanges([request.directory, queueDirectory(request.directory)]);
    const delays = asyncBackoff(request.pollMs);
    try {
      for (;;) {
        await changes.wait(delays.next());
        const slot = attempt(request);
        if (slot !== undefined) return slot;
        const failure = expired(request);
        if (failure !== undefined) throw failure;
      }
    } finally {
      changes.close();
      done();
    }
  } finally {
    leaveQueue(request);
  }
}

export function acquireSlotSync(options: SlotOptions = {}): Slot {
  const request = prepare(options);
  try {
    const immediate = attempt(request, true);
    if (immediate !== undefined) return immediate;
    const done = waitStarted();
    const delays = syncBackoff(request.pollMs);
    try {
      for (;;) {
        Atomics.wait(SLEEP_CELL, 0, 0, delays.next());
        const slot = attempt(request, true);
        if (slot !== undefined) return slot;
        const failure = expired(request);
        if (failure !== undefined) throw failure;
      }
    } finally {
      done();
    }
  } finally {
    leaveQueue(request);
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
    if (owner !== undefined && owner !== "unreadable" && holderAlive(join(slotsDirectory(root), name))) out.push({ index: Number(match[1]), pid: owner.pid });
  }
  return out.sort((a, b) => a.index - b.index);
}

