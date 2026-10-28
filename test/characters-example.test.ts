import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { judge } from "../src/judge/run.js";
import { freshDir } from "./judge/helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Entry = { cmd: string; name?: string; template?: string; preset?: string; unweighted?: number; max_influences?: number; armatures?: string[] };

const FRAMES = ["hero-walk-001-side", "hero-walk-013-front", "hero-idle-037-three-quarter", "fox-trot-007-side", "fox-idle-001-three-quarter", "chest-open-024-side"];

describe("the characters example", workBudget(420_000), () => {
  it("builds, rigs, skins and animates a humanoid, a fox and a chest by commands only, and each passes the judge with its rig, skin and animation spec", async () => {
    const out = freshDir("characters-example");
    const env = { ...process.env, BLENDWORKS_SHOT_SIZE: "128", BLENDWORKS_SHOT_SAMPLES: "4", BLENDWORKS_DEVICE: "cpu" };
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", "docs/examples/characters.py", "--", out], { env, stdio: "pipe" });
    const log = JSON.parse(readFileSync(join(out, "summary.json"), "utf8")) as Entry[];
    expect(log.filter((entry) => entry.cmd === "rig_template").map((entry) => entry.template)).toEqual(["humanoid", "quadruped", "hinge"]);
    expect(log.filter((entry) => entry.cmd === "animation_preset").map((entry) => entry.preset)).toEqual(["walk", "idle", "trot", "idle", "open"]);
    for (const entry of log.filter((item) => item.cmd === "skin_bind")) {
      expect(entry.unweighted).toBe(0);
      expect(entry.max_influences ?? 0).toBeLessThanOrEqual(4);
    }
    expect(log.filter((entry) => entry.cmd === "export").map((entry) => entry.armatures)).toEqual([["HeroRig"], ["FoxRig"], ["ChestRig"]]);
    for (const frame of FRAMES) {
      const path = join(out, `${frame}.png`);
      expect(existsSync(path), frame).toBe(true);
      expect(statSync(path).size, frame).toBeGreaterThan(1_000);
    }
    for (const asset of ["hero", "fox", "chest"]) {
      const report = await judge({ specPath: join(out, `${asset}.spec.json`), assetPath: join(out, `${asset}.glb`), outDir: join(out, `report-${asset}`) });
      expect(report.failure, asset).toBeNull();
      expect(report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule), asset).toEqual([]);
      expect(report.rules.map((rule) => rule.rule), asset).toEqual(expect.arrayContaining(["rig.requiredBones", "skin.restPose", "animation.loop", "animation.boundsWithin.size.z", "gltf.validator.maxErrors", "gltf.validator.maxWarnings"]));
      expect(existsSync(join(out, `report-${asset}`, "contact-sheet.png")), asset).toBe(true);
    }
  });
});
