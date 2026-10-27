import { basename } from "node:path";
import { vi } from "vitest";
import { acquireSlot, acquireSlotSync, type Slot } from "../../scripts/lib/slots.js";
import { currentWorkClock, envelopeMs, WAIT_FOR_SLOT_MS } from "./work-clock.js";

export { WAIT_FOR_SLOT_MS };
export const BLENDER_TEST_TIMEOUT_MS = 10 * 60_000;

let declared = false;

export function useBlenderSlot(): void {
  declared = true;
  vi.setConfig({ testTimeout: envelopeMs(BLENDER_TEST_TIMEOUT_MS), hookTimeout: envelopeMs(BLENDER_TEST_TIMEOUT_MS) });
}

export function blenderSlotHeld(): boolean {
  return declared;
}

export function defaultWorkBudgetMs(): number | undefined {
  return declared ? BLENDER_TEST_TIMEOUT_MS : undefined;
}

export function isBlenderCommand(command: string): boolean {
  return /^blender(\.exe)?$/i.test(basename(command));
}

function waitAllowanceMs(): number {
  return currentWorkClock()?.waitAllowanceMs() ?? WAIT_FOR_SLOT_MS;
}

export function takeSlot(): Promise<Slot> {
  return acquireSlot({ timeoutMs: waitAllowanceMs() });
}

export async function whileProcessRuns<T>(task: () => Promise<T>): Promise<T> {
  const slot = await takeSlot();
  try {
    return await task();
  } finally {
    slot.release();
  }
}

export async function untilProcessExits<T>(start: () => Promise<T>, exited: (started: T) => Promise<unknown>): Promise<T> {
  const slot = await takeSlot();
  try {
    const started = await start();
    void exited(started).finally(() => slot.release());
    return started;
  } catch (error) {
    slot.release();
    throw error;
  }
}

export function whileProcessRunsSync<T>(task: () => T): T {
  const slot = acquireSlotSync({ timeoutMs: waitAllowanceMs() });
  try {
    return task();
  } finally {
    slot.release();
  }
}
