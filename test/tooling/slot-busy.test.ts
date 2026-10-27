import { beforeAll, describe, expect, it, vi } from "vitest";
import { scratch } from "./probes.js";

const failures: { code: string; remaining: number } = { code: "EPERM", remaining: 0 };

let acquireSlot: typeof import("../../scripts/lib/slots.js").acquireSlot;
let acquireSlotSync: typeof import("../../scripts/lib/slots.js").acquireSlotSync;

beforeAll(async () => {
  const original = await vi.importActual<typeof import("node:fs")>("node:fs");
  vi.doMock("node:fs", () => ({
    ...original,
    writeFileSync(path: string, data: string, options: unknown) {
      if (failures.remaining > 0 && String(path).endsWith(".lock")) {
        failures.remaining -= 1;
        throw Object.assign(new Error(`${failures.code}: simulated`), { code: failures.code });
      }
      return original.writeFileSync(path, data, options as never);
    },
  }));
  vi.resetModules();
  ({ acquireSlot, acquireSlotSync } = await import("../../scripts/lib/slots.js"));
});

describe("a lock file that Windows still holds as delete-pending", () => {
  for (const code of ["EPERM", "EACCES", "EBUSY"]) {
    it(`${code} counts as busy, so acquiring retries instead of failing`, async () => {
      failures.code = code;
      failures.remaining = 3;
      const slot = await acquireSlot({ root: scratch("slot-busy"), jobs: 1, pollMs: 5, timeoutMs: 5000 });
      expect(slot.index).toBe(0);
      slot.release();
      failures.remaining = 3;
      const sync = acquireSlotSync({ root: scratch("slot-busy-sync"), jobs: 1, pollMs: 5, timeoutMs: 5000 });
      expect(sync.index).toBe(0);
      sync.release();
    });
  }

  it("any other error still fails", async () => {
    failures.code = "ENOSPC";
    failures.remaining = 1;
    await expect(acquireSlot({ root: scratch("slot-other"), jobs: 1, pollMs: 5, timeoutMs: 1000 })).rejects.toThrow(/ENOSPC/);
  });

  it("keeps waiting while the file stays busy until the timeout", async () => {
    failures.code = "EPERM";
    failures.remaining = 1_000_000;
    await expect(acquireSlot({ root: scratch("slot-timeout"), jobs: 1, pollMs: 5, timeoutMs: 100 })).rejects.toThrow(/timed out/);
    failures.remaining = 0;
  });
});
