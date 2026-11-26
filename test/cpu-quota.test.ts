import { describe, expect, it } from "vitest";
import { quotaCpus, testCpus, withThreadArguments } from "./setup/cpu-quota.js";

describe("Blender threads for test processes", () => {
  it("reads the container's CPU quota from cgroup v2 or v1", () => {
    expect(quotaCpus("400000 100000", [undefined, undefined])).toBe(4);
    expect(quotaCpus("150000 100000", [undefined, undefined])).toBe(2);
    expect(quotaCpus("max 100000", [undefined, undefined])).toBeUndefined();
    expect(quotaCpus(undefined, ["200000", "100000"])).toBe(2);
    expect(quotaCpus(undefined, ["-1", "100000"])).toBeUndefined();
    expect(quotaCpus(undefined, [undefined, undefined])).toBeUndefined();
  });

  it("adds --threads within the quota to background Blender runs unless the call gives its own", () => {
    const args = withThreadArguments(["--background", "--python", "x.py"]);
    expect(args.slice(0, 2)[0]).toBe("--threads");
    expect(Number(args[1])).toBeGreaterThanOrEqual(1);
    expect(Number(args[1])).toBeLessThanOrEqual(testCpus());
    expect(args.slice(2)).toEqual(["--background", "--python", "x.py"]);
    expect(withThreadArguments(["-t", "3", "--background"])).toEqual(["-t", "3", "--background"]);
    expect(withThreadArguments(["-e", "script"])).toEqual(["-e", "script"]);
  });
});
