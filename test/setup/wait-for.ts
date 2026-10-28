import { setTimeout as sleep } from "node:timers/promises";

export type WaitForOptions = { timeoutMs?: number; intervalMs?: number; description?: string };

export async function waitFor(condition: () => boolean | Promise<boolean>, options: WaitForOptions = {}): Promise<void> {
  const { timeoutMs = 60_000, intervalMs = 10, description = "the condition" } = options;
  const deadline = performance.now() + timeoutMs;
  while (!(await condition())) {
    if (performance.now() > deadline) throw new Error(`timed out waiting for ${description} after ${timeoutMs} ms`);
    await sleep(intervalMs);
  }
}
