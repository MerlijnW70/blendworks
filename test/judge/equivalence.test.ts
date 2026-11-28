import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, inject, it } from "vitest";
import { judge } from "../../src/judge/run.js";
import { differences, equivalenceCases, judgeCase, PLATFORM_NOISE, type FixtureFolders } from "../../scripts/lib/equivalence.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { underWorkClock, withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const BASELINE = fileURLToPath(new URL("./equivalence/fixtures.json", import.meta.url));

export const CASE_WORK_MS = 300_000;

const STORED = JSON.parse(readFileSync(BASELINE, "utf8")) as Record<string, unknown>;

let folders: FixtureFolders = {};
let baseline: Record<string, unknown> = {};

beforeAll(withWorkBudget(30_000, () => {
  const sets = inject("fixtureSets");
  if (sets === null) throw new Error("the judge fixtures are not available");
  folders = sets;
  baseline = STORED;
}));

describe("the one-pass judge against the stored reports of the judge before it", workBudget(Object.keys(STORED).length * CASE_WORK_MS), () => {
  it("judges every fixture of every fixture set, and only those", () => {
    expect(equivalenceCases(folders).map((entry) => entry.id).sort()).toEqual(Object.keys(baseline).sort());
  });

  it("gives every fixture the same rules, measured values and verdict", async () => {
    const work = freshDir("equivalence", "work");
    const found: { id: string; differences: string[] }[] = [];
    for (const entry of equivalenceCases(folders)) {
      const report = await underWorkClock(`equivalence case ${entry.id}`, CASE_WORK_MS, () => judgeCase((options) => judge(options), entry, folders, work));
      found.push({ id: entry.id, differences: differences(baseline[entry.id], report, PLATFORM_NOISE) });
    }
    expect(found.filter((entry) => entry.differences.length > 0)).toEqual([]);
  });
});
