import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, unlinkSync, utimesSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { trackHeartbeat, untrackHeartbeat } from "./heartbeat.js";
import { holderAlive, lockFile, processAlive, fresh } from "./locks.js";

export const COMPLETE_FILE = ".complete";
const KEEP_ENTRIES = 3;

export type Entry = { dir: string; generated: boolean };

export function hashFiles(files: string[], extra: string[] = []): string {
  const hash = createHash("sha256");
  const named = files.map((file) => ({ file, name: basename(file) })).sort((a, b) => a.name.localeCompare(b.name));
  for (const { file, name } of named) {
    hash.update(`file:${name}\n`);
    hash.update(readFileSync(file));
    hash.update("\n");
  }
  for (const text of extra) hash.update(`extra:${text}\n`);
  return hash.digest("hex");
}

export function entryDirectory(root: string, name: string, key: string): string {
  return join(root, name, key);
}

export function isComplete(dir: string): boolean {
  return existsSync(join(dir, COMPLETE_FILE));
}

export const LEASE_PREFIX = ".in-use-";
const leases = new Set<string>();
let leaseHookInstalled = false;

function dropLease(path: string): void {
  untrackHeartbeat(path);
  leases.delete(path);
  try {
    unlinkSync(path);
  } catch {
    return;
  }
}

export function releaseEntry(dir: string): void {
  dropLease(join(dir, `${LEASE_PREFIX}${process.pid}`));
}

function useEntry(dir: string): void {
  const now = new Date();
  try {
    utimesSync(dir, now, now);
  } catch {
    return;
  }
  const lease = join(dir, `${LEASE_PREFIX}${process.pid}`);
  if (leases.has(lease)) return;
  try {
    writeFileSync(lease, JSON.stringify({ pid: process.pid, since: Date.now() }));
  } catch {
    return;
  }
  leases.add(lease);
  trackHeartbeat(lease);
  if (leaseHookInstalled) return;
  leaseHookInstalled = true;
  process.on("exit", () => {
    for (const path of [...leases]) dropLease(path);
  });
}

export function inUse(parent: string, name: string): boolean {
  if (holderAlive(join(parent, `${name}.lock`))) return true;
  let files: string[];
  try {
    files = readdirSync(join(parent, name));
  } catch {
    return false;
  }
  return files
    .filter((file) => file.startsWith(LEASE_PREFIX))
    .some((file) => {
      const pid = Number(file.slice(LEASE_PREFIX.length));
      return Number.isInteger(pid) && processAlive(pid) && fresh(join(parent, name, file));
    });
}

function prune(parent: string, keep: string): void {
  const entries = readdirSync(parent, { withFileTypes: true })
    .filter((item) => item.isDirectory() && item.name !== keep && !item.name.includes("-tmp-"))
    .map((item) => ({ name: item.name, time: statSync(join(parent, item.name)).mtimeMs }))
    .sort((a, b) => b.time - a.time);
  for (const stale of entries.slice(KEEP_ENTRIES - 1)) if (!inUse(parent, stale.name)) rmSync(join(parent, stale.name), { recursive: true, force: true });
}

export async function ensureEntry(options: {
  root: string;
  name: string;
  key: string;
  generate: (workDir: string, finalDir: string) => Promise<void>;
}): Promise<Entry> {
  const parent = join(options.root, options.name);
  mkdirSync(parent, { recursive: true });
  const finalDir = entryDirectory(options.root, options.name, options.key);
  if (isComplete(finalDir)) {
    useEntry(finalDir);
    return { dir: finalDir, generated: false };
  }
  const lock = await lockFile(join(parent, `${options.key}.lock`));
  try {
    if (isComplete(finalDir)) {
      useEntry(finalDir);
      return { dir: finalDir, generated: false };
    }
    rmSync(finalDir, { recursive: true, force: true });
    for (const leftover of readdirSync(parent)) if (leftover.startsWith(`${options.key}-tmp-`)) rmSync(join(parent, leftover), { recursive: true, force: true });
    const workDir = join(parent, `${options.key}-tmp-${process.pid}`);
    mkdirSync(workDir, { recursive: true });
    try {
      await options.generate(workDir, finalDir);
      writeFileSync(join(workDir, COMPLETE_FILE), `${new Date().toISOString()}\n`);
      renameSync(workDir, finalDir);
    } catch (error) {
      rmSync(workDir, { recursive: true, force: true });
      throw error;
    }
    useEntry(finalDir);
    prune(parent, options.key);
    return { dir: finalDir, generated: true };
  } finally {
    lock.release();
  }
}
