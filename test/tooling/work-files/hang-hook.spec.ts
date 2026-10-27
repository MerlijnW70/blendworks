import { beforeAll, it } from "vitest";
import { useBlenderSlot } from "../../setup/slot.js";
import { withWorkBudget } from "../../setup/work-clock.js";
import { fakeBlender } from "./fake.js";

useBlenderSlot();

beforeAll(withWorkBudget(Number(process.env["BUDGET_MS"]), () => fakeBlender(Number(process.env["HOLD_MS"]))));

it("never runs, because its hook hangs", () => {});
