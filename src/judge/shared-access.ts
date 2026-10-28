import { readFileSync } from "node:fs";
import { InfrastructureError } from "./isolation.js";

const HELD_ELSEWHERE = new Set(["EBUSY", "EPERM", "EACCES"]);
export const SHARED_ACCESS_MS = 2000;
const FIRST_PAUSE_MS = 10;
const LONGEST_PAUSE_MS = 100;
const SLEEP_CELL = new Int32Array(new SharedArrayBuffer(4));

export function withSharedAccess<T>(action: () => T, platform: NodeJS.Platform = process.platform): T {
  const deadline = performance.now() + SHARED_ACCESS_MS;
  let pause = FIRST_PAUSE_MS;
  for (;;) {
    try {
      return action();
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (platform !== "win32" || code === undefined || !HELD_ELSEWHERE.has(code)) throw error;
      if (performance.now() >= deadline) throw new InfrastructureError("file_lock", `a file stayed locked by another process for more than ${SHARED_ACCESS_MS / 1000} s (${code}), so nothing was judged and this is not a verdict`);
    }
    Atomics.wait(SLEEP_CELL, 0, 0, pause);
    pause = Math.min(pause * 2, LONGEST_PAUSE_MS);
  }
}

export function readShared(path: string): Buffer {
  return withSharedAccess(() => readFileSync(path));
}
