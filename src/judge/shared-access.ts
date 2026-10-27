import { readFileSync } from "node:fs";

const HELD_ELSEWHERE = new Set(["EBUSY", "EPERM", "EACCES"]);
export const SHARED_ACCESS_MS = 2000;
const FIRST_PAUSE_MS = 10;
const LONGEST_PAUSE_MS = 100;
const SLEEP_CELL = new Int32Array(new SharedArrayBuffer(4));

export function withSharedAccess<T>(action: () => T, platform: NodeJS.Platform = process.platform): T {
  const deadline = Date.now() + SHARED_ACCESS_MS;
  let pause = FIRST_PAUSE_MS;
  for (;;) {
    try {
      return action();
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (platform !== "win32" || code === undefined || !HELD_ELSEWHERE.has(code) || Date.now() >= deadline) throw error;
    }
    Atomics.wait(SLEEP_CELL, 0, 0, pause);
    pause = Math.min(pause * 2, LONGEST_PAUSE_MS);
  }
}

export function readShared(path: string): Buffer {
  return withSharedAccess(() => readFileSync(path));
}
