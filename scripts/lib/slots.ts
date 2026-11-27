import { randomUUID } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { blenderJobs } from "../../src/blender.js";
import { trackHeartbeat, untrackHeartbeat } from "./heartbeat.js";
import { type FileLock, fresh, holderAlive, readOwner, processAlive, tryLock, waitStarted } from "./locks.js";
import { cgroupHeldMb, refusal, type Refusal, fileNeedMb, gateBudgetMb, hardLimitMb, knownPeaks, type Live, type Running } from "./memory.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";
import { asyncBackoff, syncBackoff, watchChanges } from "./slot-wait.js";
import { currentStage, recordTiming } from "./timings.js";

export type SlotOptions = { root?: string; jobs?: number; timeoutMs?: number; pollMs?: number; label?: string; file?: string; needMb?: number; budgetMb?: number; live?: () => Live | undefined };

export type Slot = { index: number; waitedMs: number; heldBackMs: number; release(): void; attach(pid: number, file?: string, shared?: boolean): void };

export type Holder = { index: number; pid: number; file: string | undefined; needMb: number | undefined; stage?: string | undefined; child: { pid: number; file: string | undefined; shared: boolean } | undefined };

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

type Request = { directory: string; jobs: number; started: number; deadline: number; pollMs: number; label: string; ticket: string; file: string; needMb: number; budgetMb: number; heldBackSince: number | undefined; heldBackMs: number; live: () => Live | undefined; refusals: Set<Refusal> };

export function cgroupLive(): Live | undefined {
  const hardMb = hardLimitMb();
  const heldMb = hardMb === undefined ? undefined : cgroupHeldMb();
  return hardMb === undefined || heldMb === undefined ? undefined : { heldMb, hardMb };
}

const EXPECT_GLOBAL = Symbol.for("expect-global");

export function testFileOfCaller(): string | undefined {
  const expectation = (globalThis as Record<symbol, unknown>)[EXPECT_GLOBAL] as { getState?: () => { testPath?: string } } | undefined;
  const path = expectation?.getState?.().testPath;
  return typeof path === "string" && path !== "" ? relative(repoRoot, path).split(sep).join("/") : undefined;
}

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
  let heldAhead = false;
  for (const name of names) {
    const match = TICKET.exec(name);
    if (match === null || name >= request.ticket) continue;
    const pid = Number(match[3]);
    if (blocking && pid === process.pid) continue;
    if (processAlive(pid) && fresh(join(queue, name))) {
      ahead += 1;
      heldAhead ||= heldByMemory(join(queue, name));
    } else removeQuietly(join(queue, name));
  }
  return heldAhead && !runningFiles(request.directory).some((entry) => entry.file === request.file) ? Number.POSITIVE_INFINITY : ahead;
}

const HELD = "held by the memory gate";

function heldByMemory(ticket: string): boolean {
  try {
    return readFileSync(ticket, "utf8") === HELD;
  } catch {
    return false;
  }
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
  const known = options.file ?? testFileOfCaller();
  const file = known ?? `unknown file in process ${process.pid}`;
  const needMb = options.needMb ?? fileNeedMb(known, knownPeaks(root));
  const budgetMb = options.budgetMb ?? gateBudgetMb();
  return { directory, jobs: options.jobs ?? blenderJobs(), started, deadline: started + (options.timeoutMs ?? 30 * 60_000), pollMs: options.pollMs ?? 40, label, ticket: joinQueue(directory), file, needMb, budgetMb, heldBackSince: undefined, heldBackMs: 0, live: options.live ?? cgroupLive, refusals: new Set() };
}

const SLOT_LOCK = /^slot-(\d+)\.lock$/;

function childPath(directory: string, index: number): string {
  return join(directory, `slot-${index}.child`);
}

function readChild(path: string): { pid: number; file: string | undefined; token: string; shared: boolean } | undefined {
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as { pid?: unknown; file?: unknown; token?: unknown; shared?: unknown };
    if (typeof parsed.pid !== "number" || typeof parsed.token !== "string") return undefined;
    return { pid: parsed.pid, file: typeof parsed.file === "string" ? parsed.file : undefined, token: parsed.token, shared: parsed.shared === true };
  } catch {
    return undefined;
  }
}

export function slotHolders(directory: string): Holder[] {
  let names: string[];
  try {
    names = readdirSync(directory);
  } catch {
    return [];
  }
  const out: Holder[] = [];
  for (const name of names) {
    const match = SLOT_LOCK.exec(name);
    if (match === null) continue;
    const path = join(directory, name);
    const owner = readOwner(path);
    if (owner === undefined || owner === "unreadable" || !holderAlive(path)) continue;
    const index = Number(match[1]);
    const child = readChild(childPath(directory, index));
    out.push({ index, pid: owner.pid, file: owner.file, needMb: owner.needMb, stage: owner.stage, child: child !== undefined && child.token === owner.token ? { pid: child.pid, file: child.file, shared: child.shared } : undefined });
  }
  return out.sort((a, b) => a.index - b.index);
}

function runningFiles(directory: string): Running[] {
  return slotHolders(directory).flatMap((holder) => (holder.file === undefined ? [] : [{ file: holder.file, needMb: holder.needMb ?? 0 }]));
}

function memoryFits(request: Request): boolean {
  const refused = refusal(runningFiles(request.directory), { file: request.file, needMb: request.needMb }, request.budgetMb, request.live());
  if (refused !== undefined) request.refusals.add(refused);
  const fits = refused === undefined;
  const now = performance.now();
  if (fits) {
    if (request.heldBackSince !== undefined) request.heldBackMs += now - request.heldBackSince;
    request.heldBackSince = undefined;
    return true;
  }
  if (request.heldBackSince === undefined) {
    request.heldBackSince = now;
    try {
      writeFileSync(join(queueDirectory(request.directory), request.ticket), HELD);
    } catch {
      return false;
    }
  }
  return fits;
}

function attempt(request: Request, blocking = false): Slot | undefined {
  attempts += 1;
  return myTurn(request, blocking) ? takeFree(request) : undefined;
}

export function gateDirectory(directory: string): string {
  const folder = `${directory}-gate`;
  mkdirSync(folder, { recursive: true });
  return folder;
}

function takeFree(request: Request): Slot | undefined {
  if (busySlots(request) >= request.jobs) return undefined;
  const gate = tryLock(join(gateDirectory(request.directory), "memory.lock"));
  if (gate === undefined) return undefined;
  try {
    if (busySlots(request) >= request.jobs) return undefined;
    return memoryFits(request) ? lockFreeSlot(request) : undefined;
  } finally {
    gate.release();
  }
}

function lockFreeSlot(request: Request): Slot | undefined {
  for (let index = 0; index < request.jobs; index += 1) {
    const lock: FileLock | undefined = tryLock(join(request.directory, `slot-${index}.lock`), { file: request.file, needMb: request.needMb, stage: currentStage() });
    if (lock === undefined) continue;
    const acquired = performance.now();
    const waitedMs = acquired - request.started;
    const stage = currentStage();
    for (const observer of acquisitionObservers) observer();
    const child = childPath(request.directory, index);
    const heldBackMs = Math.round(request.heldBackMs);
    return {
      index,
      waitedMs,
      heldBackMs,
      attach: (pid, file, shared) => writeFileSync(child, JSON.stringify({ pid, file: file ?? request.file, token: lock.token, shared: shared === true })),
      release: () => {
        if (readChild(child)?.token === lock.token) removeQuietly(child);
        if (!lock.release()) return;
        recordTiming({ kind: "process", stage, label: request.label, waitMs: Math.round(waitedMs), workMs: Math.round(performance.now() - acquired), endedAt: Date.now(), ...(heldBackMs > 0 ? { memoryWaitMs: heldBackMs, memoryReasons: [...request.refusals] } : {}) });
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

