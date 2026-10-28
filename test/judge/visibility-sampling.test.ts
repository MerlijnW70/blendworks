import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { planPass } from "../../src/judge/judge-pass.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const PROBE = fileURLToPath(new URL("./visibility_probe.py", import.meta.url));
const SET_SHA256 = "c".repeat(64);

describe("the visibility sample", () => {
  it("is seeded by the sha256 of the delivered set", () => {
    const delivery = { folder: "/delivery", main: "/delivery/crate.glb", files: [], bytes: 1, sha256: SET_SHA256, references: { files: 0, unresolved: [] } };
    const plan = planPass({ spec: { format: "glb" }, delivery, references: null, maxTriangles: 2_000_000, timeoutMs: 1000, mode: null, render: { preview: true }, visual: {} });
    expect(plan.args[plan.args.indexOf("--visibility-seed") + 1]).toBe(SET_SHA256);
  });

  it("in Blender's Python: repeats for a seed, moves with it, takes one face per stratum of space, and tests every face of a small asset", workBudget(60_000), () => {
    const folder = freshDir("visibility-sampling");
    const outPath = join(folder, "result.json");
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", PROBE, "--", SCRIPTS_DIR, outPath], { stdio: "ignore", timeout: 55_000 });
    const result = JSON.parse(readFileSync(outPath, "utf8")) as Record<string, number | boolean>;
    expect(result).toMatchObject({ sameSeed: true, otherSeed: false, count: 100, weights: 1000, perStratum: true, allWhenFew: true, directions: 64, repeatable: true });
    expect(result.sineError).toBeLessThan(1e-12);
    expect(result.unit).toBeLessThan(1e-12);
    expect(result.spread).toBeGreaterThan(0.9);
  });
});
