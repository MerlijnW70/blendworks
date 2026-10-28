import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(withWorkBudget(240_000, () => {
  ({ assets } = makeFixtureSet("character_fixtures", "characters"));
  specs = freshDir("characters", "specs");
}));

const HUMANOID = {
  size: { x: [0.5, 1.4], y: [0.2, 1.4], z: [1.6, 1.85] },
  rig: {
    required: true,
    maxBones: 64,
    requiredBones: ["hips", "spine", "head", "leftHand", "rightHand", "leftFoot", "rightFoot"],
    boneMap: { hips: ["Hips", "mixamorig:Hips"], spine: "Spine", head: "Head", leftHand: ["LeftHand", "hand.L"], rightHand: ["RightHand", "hand.R"], leftFoot: "LeftFoot", rightFoot: "RightFoot" },
  },
  skin: { maxInfluences: 4, maxUnweighted: 0, normalized: true, restPose: true },
  animation: { requiredClips: ["walk", "idle"], loop: { clips: ["walk"], tolerance: 0.001 }, maxDuration: 4, maxRootMotion: 0.05, boundsWithin: true },
};

async function judged(asset: string, rules: Record<string, unknown>, label: string, preview = true): Promise<Report> {
  const name = `${asset.replace(/\W+/g, "-")}-${label}`;
  const spec = join(specs, `${name}.spec.json`);
  writeFileSync(spec, JSON.stringify({ format: asset.split(".").pop(), views: ["front", "three-quarter"], ...rules }));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("characters", "reports", name), preview });
}

function failing(report: Report): string[] {
  return report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule);
}

describe("a humanoid built from the template, skinned and given walk and idle clips", workBudget(240_000), () => {
  it("passes the judge's rig, skin and animation rules through the full judge on the exported glb", async () => {
    const report = await judged("humanoid.glb", HUMANOID, "every-rule", false);
    expect(report.failure).toBeNull();
    expect(failing(report)).toEqual([]);
    expect(report.rules.map((rule) => rule.rule)).toEqual(expect.arrayContaining(["rig.requiredBones", "skin.maxInfluences", "skin.maxUnweighted", "skin.normalized", "skin.restPose", "animation.requiredClips", "animation.loop", "animation.maxRootMotion", "animation.boundsWithin.size.y"]));
    const { rig, skin, animation } = report.measurements!;
    expect(rig).toMatchObject({ armatures: 1, bones: 22, roots: ["Root"] });
    expect(skin).toMatchObject({ meshes: 3, unweighted: 0, notNormalized: 0, restPose: { method: "gltf", bound: true, joints: 22, jointsOff: 0 } });
    expect(skin!.maxInfluences).toBeLessThanOrEqual(4);
    expect(animation).toMatchObject({ clips: 2, names: ["idle", "walk"], fps: 24 });
    for (const clip of animation!.items) {
      expect(clip.loopError, clip.name).toBeLessThan(1e-4);
      expect(clip.rootMotion.max, clip.name).toBeLessThan(1e-6);
      expect(clip.frameRate, clip.name).toBe(24);
    }
    expect(report.renders?.status).not.toBe("failed");
  });
});

describe("breaking one property fails the matching judge rule", workBudget(240_000), () => {
  it("an unweighted vertex fails skin.maxUnweighted", async () => {
    const report = await judged("unweighted.blend", HUMANOID, "every-rule");
    expect(failing(report)).toEqual(["skin.maxUnweighted"]);
    expect(report.measurements!.skin).toMatchObject({ unweighted: 1 });
  });

  it("a fifth influence fails skin.maxInfluences", async () => {
    const report = await judged("five-influences.blend", HUMANOID, "every-rule");
    expect(failing(report)).toEqual(["skin.maxInfluences"]);
    expect(report.measurements!.skin).toMatchObject({ maxInfluences: 5 });
  });

  it("a walk whose last frame differs from its first fails animation.loop", async () => {
    const report = await judged("popping.glb", HUMANOID, "every-rule");
    expect(failing(report)).toEqual(["animation.loop"]);
    const walk = report.measurements!.animation!.items.find((clip) => clip.name === "walk")!;
    expect(walk.loopError).toBeGreaterThan(0.04);
  });

  it("a missing hand bone fails rig.requiredBones", async () => {
    const report = await judged("renamed.glb", HUMANOID, "every-rule");
    expect(failing(report)).toEqual(["rig.requiredBones"]);
    expect(report.rules.find((rule) => rule.rule === "rig.requiredBones")?.measured).toEqual({ found: 6, missing: ["leftHand"], ambiguous: [] });
  });
});
