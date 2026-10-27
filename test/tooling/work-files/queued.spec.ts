import { setTimeout as sleep } from "node:timers/promises";
import { describe, it } from "vitest";
import { useBlenderSlot } from "../../setup/slot.js";
import { workBudget } from "../../setup/work-clock.js";
import { fakeBlender } from "./fake.js";

useBlenderSlot();

describe("queued", workBudget(Number(process.env["BUDGET_MS"])), () => {
  it("waits for the slot longer than its work budget, then works within it", async () => {
    await sleep(300);
    await fakeBlender(100);
  });
});
