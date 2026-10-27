import { describe, it } from "vitest";
import { useBlenderSlot } from "../../setup/slot.js";
import { workBudget } from "../../setup/work-clock.js";
import { fakeBlender } from "./fake.js";

useBlenderSlot();

describe("hang", workBudget(Number(process.env["BUDGET_MS"])), () => {
  it("works past its budget", async () => {
    await fakeBlender(Number(process.env["HOLD_MS"]));
  });
});
