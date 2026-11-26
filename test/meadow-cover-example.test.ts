import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; count?: number; budget?: number; near?: number; populations?: Record<string, number>; contact_mean?: number; instances?: number };
type Spread = { mean: number; std: number; green: number };
type Summary = { commands: Entry[]; before: Record<string, Spread>; after: Record<string, Spread> };
type Report = { issues: { numErrors: number; numWarnings: number; messages: { code: string; message: string }[] } };
type Validator = { validateBytes(data: Uint8Array, options?: Record<string, unknown>): Promise<Report> };

const BUDGET = 15_000;

describe("the meadow cover example", workBudget(300_000), () => {
  it("dresses a meadow with a tree and rocks by commands only, keeps its budget, changes the renders and exports a valid instanced glb", async () => {
    const out = freshDir("meadow-cover-example");
    const env = { ...process.env, BLENDWORKS_TERRAIN_RESOLUTION: "41", BLENDWORKS_SHOT_SIZE: "96", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_TREE_DETAIL: "0.1", BLENDWORKS_COVER_BUDGET: String(BUDGET), BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/meadow_cover.py", "--", out], { env, stdio: "pipe" });
    const summary = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Summary;
    const cover = summary.commands.filter((entry) => entry.cmd === "ground_cover");
    expect(cover).toHaveLength(1);
    expect(cover[0]?.budget).toBe(BUDGET);
    expect(cover[0]?.count).toBeLessThanOrEqual(BUDGET);
    expect(cover[0]?.count).toBeGreaterThan(0.9 * BUDGET);
    expect(Object.keys(cover[0]?.populations ?? {})).toEqual(expect.arrayContaining(["short_grass", "tall_grass", "daisies", "fallen_leaves", "pebbles"]));
    expect(cover[0]?.contact_mean).toBeGreaterThan(0);
    const exported = summary.commands.find((entry) => entry.cmd === "ground_cover_export");
    expect(exported?.instances).toBe(cover[0]?.count);
    for (const camera of ["eye", "wide"]) {
      for (const stage of ["before", "after"]) expect(statSync(join(out, `${camera}-${stage}.png`)).size, `${camera}-${stage}`).toBeGreaterThan(1_000);
      expect(Math.abs(summary.after[camera]!.mean - summary.before[camera]!.mean), camera).toBeGreaterThan(0.01);
    }
    expect(existsSync(join(out, "meadow-cover.blend"))).toBe(true);
    const validator = createRequire(import.meta.url)("gltf-validator") as Validator;
    const report = await validator.validateBytes(new Uint8Array(readFileSync(join(out, "meadow-cover.glb"))), { writeTimestamp: false });
    expect(report.issues.numErrors, JSON.stringify(report.issues.messages.slice(0, 5))).toBe(0);
  });
});
