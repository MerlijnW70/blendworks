import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { randomBytes } from "node:crypto";

export interface CacheEntry {
  fetchedAt: number;
  data: unknown;
}

const KEY = /^[a-z]+-[A-Za-z0-9_-]{1,80}$/;

export class DiskCache {
  constructor(
    private readonly dir: () => string,
    private readonly ttlMs: number,
    private readonly now: () => number,
  ) {}

  private path(key: string): string {
    if (!KEY.test(key)) throw new Error(`invalid cache key ${key}`);
    return join(this.dir(), `${key}.json`);
  }

  async read(key: string): Promise<unknown | undefined> {
    let text: string;
    try {
      text = await readFile(this.path(key), "utf8");
    } catch {
      return undefined;
    }
    let entry: unknown;
    try {
      entry = JSON.parse(text);
    } catch {
      return undefined;
    }
    if (typeof entry !== "object" || entry === null) return undefined;
    const { fetchedAt, data } = entry as Partial<CacheEntry>;
    if (typeof fetchedAt !== "number") return undefined;
    const age = this.now() - fetchedAt;
    if (age < 0 || age >= this.ttlMs) return undefined;
    return data;
  }

  async write(key: string, data: unknown): Promise<void> {
    const target = this.path(key);
    await mkdir(dirname(target), { recursive: true });
    const temporary = `${target}.${randomBytes(6).toString("hex")}.part`;
    const entry: CacheEntry = { fetchedAt: this.now(), data };
    try {
      await writeFile(temporary, JSON.stringify(entry));
      await rename(temporary, target);
    } catch (error) {
      await rm(temporary, { force: true });
      throw error;
    }
  }

  async forget(key: string): Promise<void> {
    await rm(this.path(key), { force: true });
  }
}
