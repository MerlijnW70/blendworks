import { setTimeout as sleep } from "node:timers/promises";
import { beforeAll, expect, it } from "vitest";
import { useBlenderSlot } from "../../setup/slot.js";
import { withWorkBudget } from "../../setup/work-clock.js";
import { fakeBlender } from "./fake.js";

useBlenderSlot();

let ran = false;

beforeAll(
  withWorkBudget(Number(process.env["BUDGET_MS"]), async () => {
    await sleep(600);
    await fakeBlender(100);
    ran = true;
  }),
);

it("ran its hook after waiting for the slot", () => {
  expect(ran).toBe(true);
});
