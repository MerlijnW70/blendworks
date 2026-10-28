import { watch, type FSWatcher } from "node:fs";

const GROWTH = 1.5;
const ASYNC_CEILING_MS = 500;
const SYNC_CEILING_MS = 100;

export type Backoff = { next(): number };

export function backoff(initialMs: number, ceilingMs: number): Backoff {
  let delay = initialMs;
  const limit = Math.max(initialMs, Math.min(initialMs * 10, ceilingMs));
  return {
    next() {
      const current = delay;
      delay = Math.min(limit, Math.ceil(delay * GROWTH));
      return current;
    },
  };
}

export const asyncBackoff = (pollMs: number): Backoff => backoff(pollMs, ASYNC_CEILING_MS);
export const syncBackoff = (pollMs: number): Backoff => backoff(pollMs, SYNC_CEILING_MS);

export type Changes = { wait(ms: number): Promise<void>; close(): void };

export function watchChanges(folders: string[]): Changes {
  const watchers: FSWatcher[] = [];
  let signalled = false;
  let wake: (() => void) | undefined;
  const onChange = (): void => {
    signalled = true;
    wake?.();
  };
  for (const folder of folders) {
    try {
      const watcher = watch(folder, { persistent: false }, onChange);
      watcher.on("error", () => undefined);
      watchers.push(watcher);
    } catch {
      continue;
    }
  }
  return {
    wait(ms) {
      if (signalled) {
        signalled = false;
        return Promise.resolve();
      }
      return new Promise((resolve) => {
        const finish = (): void => {
          clearTimeout(timer);
          wake = undefined;
          signalled = false;
          resolve();
        };
        const timer = setTimeout(finish, ms);
        wake = finish;
      });
    },
    close() {
      for (const watcher of watchers) watcher.close();
    },
  };
}
