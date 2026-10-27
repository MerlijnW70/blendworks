import { randomUUID } from "node:crypto";
import { readFileSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const UNREADABLE_GRACE_MS = 5_000;
const RECLAIM_GRACE_MS = 10_000;
const BUSY_CODES = new Set(["EEXIST", "EPERM", "EACCES", "EBUSY"]);

export type Owner = { pid: number; token: string; since: number };

export type FileLock = { path: string; token: string; release(): boolean };

export type WaitObserver = { waiting(): void; waited(waitedMs: number): void };

const waitObservers = new Set<WaitObserver>();

export function observeWaits(observer: WaitObserver): () => void {
  waitObservers.add(observer);
  return () => waitObservers.delete(observer);
}

export function waitStarted(): () => number {
  const started = performance.now();
  for (const observer of waitObservers) observer.waiting();
  return () => {
    const waitedMs = performance.now() - started;
    for (const observer of waitObservers) observer.waited(waitedMs);
    return waitedMs;
  };
}

export function processAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

export function readOwner(path: string): Owner | "unreadable" | undefined {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    return "unreadable";
  }
  try {
    const parsed = JSON.parse(text) as Partial<Owner>;
    if (typeof parsed.pid === "number" && typeof parsed.token === "string") return { pid: parsed.pid, token: parsed.token, since: parsed.since ?? 0 };
  } catch {
    return "unreadable";
  }
  return "unreadable";
}

function ageMs(path: string): number {
  try {
    return Date.now() - statSync(path).mtimeMs;
  } catch {
    return 0;
  }
}

function createExclusive(path: string, owner: Owner): boolean {
  try {
    writeFileSync(path, JSON.stringify(owner), { flag: "wx" });
    return true;
  } catch (error) {
    if (BUSY_CODES.has((error as NodeJS.ErrnoException).code ?? "")) return false;
    throw error;
  }
}

function removeIfOwned(path: string, token: string): void {
  const owner = readOwner(path);
  if (owner !== undefined && owner !== "unreadable" && owner.token === token) {
    try {
      unlinkSync(path);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
}

function isStale(path: string): boolean {
  const owner = readOwner(path);
  if (owner === undefined) return false;
  if (owner === "unreadable") return ageMs(path) > UNREADABLE_GRACE_MS;
  return !processAlive(owner.pid);
}

function reclaimStale(path: string): void {
  const guard = `${path}.reclaim`;
  const mine: Owner = { pid: process.pid, token: randomUUID(), since: Date.now() };
  if (!createExclusive(guard, mine)) {
    if (ageMs(guard) > RECLAIM_GRACE_MS) {
      try {
        unlinkSync(guard);
      } catch {
        return;
      }
    }
    return;
  }
  try {
    if (isStale(path)) {
      try {
        unlinkSync(path);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
    }
  } finally {
    removeIfOwned(guard, mine.token);
  }
}

const held = new Set<FileLock>();
let exitHookInstalled = false;

function installExitHook(): void {
  if (exitHookInstalled) return;
  exitHookInstalled = true;
  process.on("exit", () => {
    for (const lock of [...held]) lock.release();
  });
}

export function tryLock(path: string): FileLock | undefined {
  const owner: Owner = { pid: process.pid, token: randomUUID(), since: Date.now() };
  if (!createExclusive(path, owner)) {
    if (isStale(path)) reclaimStale(path);
    return undefined;
  }
  installExitHook();
  const lock: FileLock = {
    path,
    token: owner.token,
    release() {
      if (!held.delete(lock)) return false;
      removeIfOwned(path, owner.token);
      return true;
    },
  };
  held.add(lock);
  return lock;
}

export async function lockFile(path: string, options: { timeoutMs?: number; pollMs?: number } = {}): Promise<FileLock> {
  const immediate = tryLock(path);
  if (immediate !== undefined) return immediate;
  const deadline = Date.now() + (options.timeoutMs ?? 30 * 60_000);
  const done = waitStarted();
  try {
    for (;;) {
      await sleep(options.pollMs ?? 40);
      const lock = tryLock(path);
      if (lock !== undefined) return lock;
      if (Date.now() > deadline) throw new Error(`timed out waiting, not working: waited for the lock ${path}`);
    }
  } finally {
    done();
  }
}
