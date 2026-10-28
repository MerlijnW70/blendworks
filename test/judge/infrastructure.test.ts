import { describe, expect, it } from "vitest";
import { EvidenceLedger, infrastructureError, isInfrastructure, unsettledBy } from "../../src/judge/infrastructure.js";
import { InfrastructureError } from "../../src/judge/isolation.js";
import { outOfMemory } from "../../src/judge/onepass.js";
import { withSharedAccess } from "../../src/judge/shared-access.js";
import type { RuleResult } from "../../src/judge/shape-rules.js";

const TIMEOUT = { stage: "render" as const, code: "timeout", message: "Blender took longer than 0.001 s and was stopped" };

function rule(name: string, pass: boolean): RuleResult {
  return { rule: name, measured: null, limit: null, pass };
}

function thrown(action: () => unknown): unknown {
  try {
    action();
  } catch (error) {
    return error;
  }
  return null;
}

describe("infrastructure outcomes are not verdicts", () => {
  it("names a stage timeout, a memory cap and a file lock as infrastructure, and nothing else", () => {
    for (const code of ["timeout", "memory_cap", "file_lock"]) expect(isInfrastructure({ stage: "measure", code, message: "" })).toBe(true);
    for (const code of ["crashed", "changed", "malformed", "non_finite", "too_many_triangles", "image_too_large", "unbounded_geometry"]) expect(isInfrastructure({ stage: "measure", code, message: "" })).toBe(false);
    expect(isInfrastructure(null)).toBe(false);
    const error = infrastructureError({ stage: "measure", code: "memory_cap", message: "out of memory" });
    expect(error).toBeInstanceOf(InfrastructureError);
    expect(error.code).toBe("memory_cap");
    expect(error.message).toContain("this is not a verdict");
  });

  it("leaves the verdict unsettled only when every failing rule needs the evidence that a limit cost", () => {
    const lost = new Set(["render", "visual"] as const);
    expect(unsettledBy([rule("renders.required", false), rule("size.x", true)], lost)).toBe(true);
    expect(unsettledBy([rule("renders.required", false), rule("natural.repetition", false), rule("visual.minScore", false)], lost)).toBe(true);
    expect(unsettledBy([rule("renders.required", false), rule("size.x", false)], lost)).toBe(false);
    expect(unsettledBy([rule("renders.required", true), rule("size.x", true)], lost)).toBe(false);
    expect(unsettledBy([rule("renders.required", false)], new Set(["visual"] as const))).toBe(false);
    expect(unsettledBy([rule("visual.minScore", false)], new Set(["visual"] as const))).toBe(true);
    expect(unsettledBy([rule("renders.required", false)], new Set())).toBe(false);
  });

  it("throws an infrastructure error from the ledger for a render timeout behind renders.required, and never for a crash", () => {
    const timedOut = new EvidenceLedger();
    timedOut.note(TIMEOUT, ["render", "visual"]);
    expect(thrown(() => timedOut.settle([rule("renders.required", false)]))).toMatchObject({ name: "InfrastructureError", code: "timeout" });
    expect(thrown(() => timedOut.settle([rule("renders.required", false), rule("triangles.max", false)]))).toBeNull();
    const crashed = new EvidenceLedger();
    crashed.note({ ...TIMEOUT, code: "crashed" }, ["render", "visual"]);
    expect(thrown(() => crashed.settle([rule("renders.required", false)]))).toBeNull();
  });

  it("reads a Blender that ran out of memory from its exit and its output", () => {
    expect(outOfMemory(null, "SIGKILL", "")).toBe(true);
    expect(outOfMemory(0xc0000017, null, "")).toBe(true);
    expect(outOfMemory(-1073741801, null, "")).toBe(true);
    expect(outOfMemory(139, null, "Malloc returns null: len=17179869184 in BLI_array, total 2147483648")).toBe(true);
    expect(outOfMemory(134, null, "terminate called after throwing an instance of 'std::bad_alloc'")).toBe(true);
    expect(outOfMemory(3, null, "Traceback (most recent call last):")).toBe(false);
    expect(outOfMemory(139, "SIGSEGV", "Writing: /tmp/blender.crash.txt")).toBe(false);
  });

  it("reports a file held past its bound on Windows as an infrastructure error, and rethrows other errors", () => {
    let attempts = 0;
    const held = () => {
      attempts += 1;
      throw Object.assign(new Error("EBUSY: resource busy or locked"), { code: "EBUSY" });
    };
    expect(thrown(() => withSharedAccess(held, "win32"))).toMatchObject({ name: "InfrastructureError", code: "file_lock" });
    expect(attempts).toBeGreaterThan(1);
    expect(thrown(() => withSharedAccess(held, "linux"))).toMatchObject({ code: "EBUSY" });
    const missing = () => {
      throw Object.assign(new Error("ENOENT"), { code: "ENOENT" });
    };
    expect(thrown(() => withSharedAccess(missing, "win32"))).toMatchObject({ code: "ENOENT" });
  });
});
