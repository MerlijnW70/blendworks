import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { detectTools, planSandbox, runSandboxed } from "../../src/judge/sandbox.js";
import { freshDir, makeFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const PROBE = fileURLToPath(new URL("./stage_isolation_probe.py", import.meta.url));
const LIMITS = { timeoutMs: 150_000, memoryBytes: 4096 * 1024 * 1024 };

type Scope = { before: unknown; after: unknown; changedInside: boolean };
type Silhouettes = { frame: unknown; views: [string, number, string][] };
type Probe = { clean: string; tampered: string; alone: string; cleanSilhouettes: Silhouettes; tamperedSilhouettes: Silhouettes; views: [string, string]; scope: Scope };

let probe: Probe;

beforeAll(withWorkBudget(150_000, async () => {
  const { assets } = makeFixtures("stage-isolation");
  const dir = freshDir("stage-isolation", "probe");
  const plan = planSandbox(blenderPath(), PROBE, [SCRIPTS_DIR, join(assets, "crate.glb"), dir], LIMITS, detectTools(), "cpu");
  const run = await runSandboxed(plan, dir);
  probe = JSON.parse(readFileSync(join(dir, "probe.json"), "utf8")) as Probe;
  expect(run.timedOut).toBe(false);
}));

describe("one judge process keeps its stages apart", workBudget(60_000), () => {
  it("writes the same measurements when a render stage moves every mesh and rewrites the measurements it is handed", () => {
    expect(probe.views[0]).not.toBe(probe.views[1]);
    expect(probe.tampered).toBe(probe.clean);
    expect(JSON.parse(probe.clean).measurements.size).not.toEqual([0, 0, 0]);
  });

  it("measures the same in a pass that renders as in a pass that only measures", () => {
    expect(probe.alone).toBe(probe.clean);
  });

  it("keeps the silhouettes the reference stage made before the render stage ran", () => {
    expect(probe.tamperedSilhouettes).toEqual(probe.cleanSilhouettes);
    expect(probe.cleanSilhouettes.views.map(([view]) => view)).toEqual(["front", "left"]);
  });

  it("renders each stage in its own scene copy and leaves the judged scene as it found it", () => {
    expect(probe.scope.changedInside).toBe(true);
    expect(probe.scope.after).toEqual(probe.scope.before);
  });
});
