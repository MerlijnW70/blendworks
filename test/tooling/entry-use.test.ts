import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, statSync, utimesSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { COMPLETE_FILE, ensureEntry, inUse, LEASE_PREFIX, releaseEntry } from "../../scripts/lib/entry-cache.js";
import { tryLock } from "../../scripts/lib/locks.js";
import { scratch } from "./probes.js";

const DAY_MS = 86_400_000;

async function make(root: string, key: string): Promise<string> {
  return (await ensureEntry({ root, name: "set", key, generate: async (work) => writeFileSync(join(work, "file.txt"), key) })).dir;
}

function age(dir: string, days: number): void {
  const then = new Date(Date.now() - days * DAY_MS);
  utimesSync(dir, then, then);
}

function plant(root: string, key: string, days: number): string {
  const dir = join(root, "set", key);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, COMPLETE_FILE), "");
  age(dir, days);
  return dir;
}

function deadPid(): number {
  const child = spawnSync(process.execPath, ["-e", "process.stdout.write(String(process.pid))"], { encoding: "utf8" });
  return Number(child.stdout);
}

describe("entries of the cache that are in use", () => {
  it("a cache hit refreshes the age of the entry", async () => {
    const root = scratch("hit-age");
    const dir = plant(root, "k1", 10);
    const old = statSync(dir).mtimeMs;
    expect((await ensureEntry({ root, name: "set", key: "k1", generate: async () => undefined })).generated).toBe(false);
    expect(statSync(dir).mtimeMs - old).toBeGreaterThan(9 * DAY_MS);
  });

  it("pruning removes the oldest entries beyond the newest three", async () => {
    const root = scratch("prune");
    const dirs = [plant(root, "a", 4), plant(root, "b", 3), plant(root, "c", 2)];
    await make(root, "d");
    expect(dirs.map((dir) => existsSync(dir))).toEqual([false, true, true]);
  });

  it("pruning keeps an entry that a hit just refreshed, however old it was", async () => {
    const root = scratch("prune-hit");
    const first = plant(root, "a", 10);
    plant(root, "b", 3);
    plant(root, "c", 2);
    await make(root, "a");
    releaseEntry(first);
    await make(root, "d");
    expect([existsSync(first), existsSync(join(root, "set", "b"))]).toEqual([true, false]);
  });

  it("pruning keeps an entry whose key is locked by a live process, and an entry a live process uses", async () => {
    const root = scratch("prune-use");
    const locked = plant(root, "locked", 10);
    const used = plant(root, "used", 9);
    writeFileSync(join(used, `${LEASE_PREFIX}${process.pid}`), "{}");
    age(used, 9);
    const plain = plant(root, "plain", 8);
    plant(root, "p2", 7);
    plant(root, "p3", 6);
    const lock = tryLock(join(root, "set", "locked.lock"));
    expect(lock).toBeDefined();
    expect(inUse(join(root, "set"), "locked")).toBe(true);
    expect(inUse(join(root, "set"), "used")).toBe(true);
    expect(inUse(join(root, "set"), "plain")).toBe(false);
    await make(root, "new");
    lock?.release();
    expect([existsSync(locked), existsSync(used), existsSync(plain)]).toEqual([true, true, false]);
  });

  it("pruning removes an old entry whose user died", async () => {
    const root = scratch("prune-dead");
    const dead = plant(root, "dead", 10);
    writeFileSync(join(dead, `${LEASE_PREFIX}${deadPid()}`), "{}");
    age(dead, 10);
    plant(root, "b", 2);
    plant(root, "c", 1);
    expect(inUse(join(root, "set"), "dead")).toBe(false);
    await make(root, "new");
    expect(existsSync(dead)).toBe(false);
  });

  it("a process that generated or hit an entry leases it for as long as it lives", async () => {
    const root = scratch("lease");
    const dir = await make(root, "k");
    expect(inUse(join(root, "set"), "k")).toBe(true);
    expect(existsSync(join(dir, `${LEASE_PREFIX}${process.pid}`))).toBe(true);
    releaseEntry(dir);
    expect(inUse(join(root, "set"), "k")).toBe(false);
  });
});
