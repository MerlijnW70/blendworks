import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { repoRoot } from "../../scripts/lib/paths.js";
import { freshDir } from "../judge/helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const PROBE = fileURLToPath(new URL("./uv_pack_probe.py", import.meta.url));
const BEFORE = { coverage: 0.236557, trials: 7 };
const MAX_PACKS = 12;
const GAP_SHARE = 0.9;

type Probe = { gap: number; seconds: number; packs: number; trials: number; best: { coverage: number; margin: number; inside: boolean }; density: { min: number; max: number }; overlap: number; outside: boolean };

let probe: Probe;

beforeAll(withWorkBudget(180_000, () => {
  const out = join(freshDir("uv-pack"), "probe.json");
  execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", PROBE, "--", repoRoot, out], { stdio: "ignore", timeout: 170_000 });
  probe = JSON.parse(readFileSync(out, "utf8")) as Probe;
}));

describe("uv_pack with a coverage target on the notched ring of test_uv_coverage", workBudget(30_000), () => {
  it("covers at least as much of the square as the search before it, inside the square and without overlap", () => {
    expect(probe.best.coverage).toBeGreaterThanOrEqual(BEFORE.coverage);
    expect(probe.best.inside).toBe(true);
    expect(probe.overlap).toBeLessThan(0.01);
    expect(probe.outside).toBe(false);
    expect(probe.density.max / probe.density.min).toBeLessThan(1.5);
  });

  it("keeps islands about twice the margin apart, as Blender's exact margin does, which leaves 0.96 of it with 90 degree turns", () => {
    expect(probe.gap).toBeGreaterThanOrEqual(2 * probe.best.margin * GAP_SHARE);
  });

  it("runs the same seven trials in at most 12 packs, which is what made the search at least 4 times faster than the 23.75 s it took before", () => {
    expect(probe.trials).toBe(BEFORE.trials);
    expect(probe.packs).toBeGreaterThan(0);
    expect(probe.packs).toBeLessThanOrEqual(MAX_PACKS);
  });
});
