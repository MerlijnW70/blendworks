import { it } from "vitest";
import { useBlenderSlot } from "../../setup/slot.js";
import { fakeBlender } from "./fake.js";

useBlenderSlot();

it("holds the only Blender slot for a while", async () => {
  await fakeBlender(Number(process.env["HOLD_MS"]));
});
