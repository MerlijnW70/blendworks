import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { lockFile } from "./locks.js";

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

function prune(parent: string, keep: string): void {
  const entries = readdirSync(parent, { withFileTypes: true })
    .filter((item) => item.isDirectory() && item.name !== keep && !item.name.includes("-tmp-"))
    .map((item) => ({ name: item.name, time: statSync(join(parent, item.name)).mtimeMs }))
    .sort((a, b) => b.time - a.time);
  for (const stale of entries.slice(KEEP_ENTRIES - 1)) rmSync(join(parent, stale.name), { recursive: true, force: true });
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
  if (isComplete(finalDir)) return { dir: finalDir, generated: false };
  const lock = await lockFile(join(parent, `${options.key}.lock`));
  try {
    if (isComplete(finalDir)) return { dir: finalDir, generated: false };
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
    prune(parent, options.key);
    return { dir: finalDir, generated: true };
  } finally {
    lock.release();
  }
}
