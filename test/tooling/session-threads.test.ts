import { availableParallelism } from "node:os";
import { describe, expect, it } from "vitest";
import { blenderThreads } from "../../src/blender.js";
import { sessionArguments } from "../../src/session.js";

describe("the threads of a session's Blender", () => {
  it("are capped like every other Blender when BLENDWORKS_JOBS shares the machine", () => {
    const args = sessionArguments("/work", false, { BLENDWORKS_JOBS: "2" });
    expect(args.slice(0, 4)).toEqual(["--background", "--factory-startup", "--threads", String(blenderThreads(2, availableParallelism()))]);
    expect(sessionArguments("/work", false, { BLENDWORKS_JOBS: "1" })).toContain(String(blenderThreads(1, availableParallelism())));
  });

  it("are left to Blender when BLENDWORKS_JOBS is not set, so a desktop session renders at full speed", () => {
    expect(sessionArguments("/work", true, {})).not.toContain("--threads");
    expect(sessionArguments("/work", true, { BLENDWORKS_JOBS: "" })).not.toContain("--threads");
    expect(sessionArguments("/work", true, {}).at(-1)).toBe("--allow-python");
  });
});
