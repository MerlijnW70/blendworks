import { afterAll, beforeAll } from "vitest";
import { acquireSlot, type Slot } from "../../scripts/lib/slots.js";

const WAIT_FOR_SLOT_MS = 45 * 60_000;

let current: Slot | undefined;

export function blenderSlotHeld(): boolean {
  return current !== undefined;
}

export function useBlenderSlot(): void {
  beforeAll(async () => {
    current = await acquireSlot({ timeoutMs: WAIT_FOR_SLOT_MS });
  }, WAIT_FOR_SLOT_MS + 10_000);
  afterAll(() => {
    current?.release();
    current = undefined;
  });
}
