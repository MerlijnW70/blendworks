import { vi } from "vitest";
import "./process-slots.js";
import { whileProcessRuns } from "./slot.js";

vi.mock("../../src/judge/version.js", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../src/judge/version.js")>();
  const seen = new Map<string, Promise<string>>();
  return {
    ...original,
    blenderVersion(blender: string): Promise<string> {
      const known = seen.get(blender);
      if (known !== undefined) return known;
      const started = whileProcessRuns(() => original.blenderVersion(blender));
      seen.set(blender, started);
      started.catch(() => seen.delete(blender));
      return started;
    },
  };
});
