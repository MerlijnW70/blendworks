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

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtureSet("rig_fixtures", "motion"));
  specs = freshDir("motion", "specs");
}));

const SIZE = { x: [0.4, 0.5], y: [0.1, 0.9], z: [1.6, 1.75] };

const EVERY_RULE = {
  size: SIZE,
  rig: { required: true, maxBones: 10, requiredBones: ["hips", "head", "thigh.L", "thigh.R"] },
  skin: { maxInfluences: 4, maxUnweighted: 0, normalized: true, restPose: true },
  animation: { requiredClips: ["walk"], loop: true, maxDuration: 1.5, maxRootMotion: 0.05, boundsWithin: true },
};

const STRIDE = 0.4;
const LEG = 0.9;
const HALF_DEPTH = 0.05;
const SWING_Y = LEG * Math.sin(STRIDE) + HALF_DEPTH * Math.cos(STRIDE);
const FIRST_STEP = STRIDE / 6;
const DIP = LEG - HALF_DEPTH * Math.sin(FIRST_STEP) - LEG * Math.cos(FIRST_STEP);

async function judged(asset: string, rules: Record<string, unknown>, label: string): Promise<Report> {
  const name = `${asset.replace(/\W+/g, "-")}-${label}`;
  const spec = join(specs, `${name}.spec.json`);
  writeFileSync(spec, JSON.stringify({ format: asset.split(".").pop(), views: ["front"], ...rules }));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("motion", "reports", name), preview: true });
}

function failing(report: Report): string[] {
  return report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule);
}

async function caughtOnlyBy(asset: string, guard: Record<string, unknown>, expected: string[]): Promise<Report> {
  const guarded = await judged(asset, guard, "guarded");
  expect(guarded.failure).toBeNull();
  expect(failing(guarded)).toEqual(expected);
  const unguarded = await judged(asset, {}, "unguarded");
  expect(unguarded.failure).toBeNull();
  expect(unguarded.passed).toBe(true);
  return guarded;
}

function measured(report: Report, rule: string): unknown {
  return report.rules.find((entry) => entry.rule === rule)?.measured;
}

describe("the rigged figure", workBudget(180_000), () => {
  it("passes every rig, skin and animation rule, with the values worked out by hand", async () => {
    const report = await judged("figure.glb", EVERY_RULE, "every-rule");
    expect(report.failure).toBeNull();
    expect(failing(report)).toEqual([]);
    expect(report.rules.map((rule) => rule.rule)).toEqual([
      "format",
      "size.x",
      "size.y",
      "size.z",
      "rig.required",
      "rig.maxBones",
      "rig.requiredBones",
      "skin.maxInfluences",
      "skin.maxUnweighted",
      "skin.normalized",
      "skin.restPose",
      "animation.requiredClips",
      "animation.loop",
      "animation.maxDuration",
      "animation.maxRootMotion",
      "animation.boundsWithin.size.x",
      "animation.boundsWithin.size.y",
      "animation.boundsWithin.size.z",
    ]);
    const { rig, skin, animation } = report.measurements!;
    expect(rig).toMatchObject({ armatures: 1, bones: 9, deformBones: 9, depth: 3, roots: ["hips"] });
    expect(skin).toMatchObject({ meshes: 1, maxInfluences: 2, unweighted: 0, notNormalized: 0, restPose: { method: "gltf", bound: true, joints: 9, jointsOff: 0 } });
    expect(animation).toMatchObject({ clips: 1, names: ["walk"], fps: 24 });
    const walk = animation!.items[0]!;
    expect(walk).toMatchObject({ name: "walk", duration: 1, frameRate: 24, start: 1, end: 25, samples: 25, keyTimes: 25, loopError: 0, rootMotion: { max: 0 } });
    expect(report.measurements!.size).toEqual([0.46, 0.2, 1.7]);
    expect(animation!.size![0]).toBeCloseTo(0.46, 5);
    expect(animation!.size![1]).toBeCloseTo(2 * SWING_Y, 5);
    expect(animation!.size![2]).toBeCloseTo(1.7 - DIP, 5);
  });

  it("gives a spec without the new groups the report it gave before: no new measurements and no reference", async () => {
    const report = await judged("figure.glb", { size: SIZE }, "old-spec");
    expect(report.passed).toBe(true);
    expect(report.rules.map((rule) => rule.rule)).toEqual(["format", "size.x", "size.y", "size.z"]);
    expect(Object.keys(report.measurements!).filter((key) => ["rig", "skin", "animation", "vertexColors"].includes(key))).toEqual([]);
    expect("reference" in report).toBe(false);
    expect(report.summary).not.toMatch(/rig:|skin:|animation:|reference:/);
  });

  it("measures the same rig, skin and clip from the .blend, with Blender's own keys and the scene's frame rate", async () => {
    const report = await judged("figure.blend", EVERY_RULE, "every-rule");
    expect(failing(report)).toEqual([]);
    expect(report.measurements!.skin).toMatchObject({ vertices: 56, maxInfluences: 2, restPose: { method: "blend", bound: true, joints: 9 } });
    expect(report.measurements!.animation!.items[0]).toMatchObject({ duration: 1, frameRate: 24, keyframes: 16, keyTimes: 4, channels: 4, samples: 25, loopError: 0 });
    expect(report.measurements!.animation!.size![1]).toBeCloseTo(2 * SWING_Y, 5);
  });
});

describe("broken figures fail their rule, and pass once the rule is removed", workBudget(180_000), () => {
  it("five bones on the left knee: 5 influences, over the 4 game engines take", async () => {
    const report = await caughtOnlyBy("figure-five.glb", { skin: { maxInfluences: 4 } }, ["skin.maxInfluences"]);
    expect(measured(report, "skin.maxInfluences")).toBe(5);
  });

  it("a head left out of every vertex group: its 8 vertices are unweighted", async () => {
    const report = await caughtOnlyBy("figure-unweighted.blend", { skin: { maxUnweighted: 0 } }, ["skin.maxUnweighted"]);
    expect(measured(report, "skin.maxUnweighted")).toBe(8);
  });

  it("four shoulder vertices weighted 0.6 in all: 0.4 off a sum of 1", async () => {
    const report = await caughtOnlyBy("figure-unnormalised.blend", { skin: { normalized: true } }, ["skin.normalized"]);
    expect(measured(report, "skin.normalized")).toEqual({ notNormalized: 4, tolerance: 0.01 });
    const lenient = await judged("figure-unnormalised.blend", { skin: { normalized: { tolerance: 0.4 } } }, "lenient");
    expect(failing(lenient)).toEqual([]);
  });

  it("a walk that ends with the legs 0.2 rad apart from where it starts: the feet jump 2 r sin(0.1)", async () => {
    const report = await caughtOnlyBy("figure-nonloop.glb", { animation: { loop: true } }, ["animation.loop"]);
    const jump = 2 * Math.hypot(HALF_DEPTH, LEG) * Math.sin(0.1);
    const walk = report.measurements!.animation!.items[0]!;
    expect(walk.loopError).toBeCloseTo(jump, 5);
    const lenient = await judged("figure-nonloop.glb", { animation: { loop: { tolerance: 0.18 } } }, "lenient");
    expect(failing(lenient)).toEqual([]);
  });

  it("two strides that travel 1 m: root motion 1 m, 2 s long, and 0.75 m more depth over the clip", async () => {
    const guard = { size: SIZE, animation: { boundsWithin: true, maxRootMotion: 0.05, maxDuration: 1.5 } };
    const report = await caughtOnlyBy("figure-drift.glb", guard, ["animation.maxDuration", "animation.maxRootMotion", "animation.boundsWithin.size.y"]);
    const walk = report.measurements!.animation!.items[0]!;
    expect(walk).toMatchObject({ duration: 2, rootMotion: { max: 1, horizontal: 1, vertical: 0 } });
    expect(report.measurements!.animation!.size![1]).toBeCloseTo(2 * SWING_Y + 0.75, 5);
    expect(report.measurements!.size).toEqual([0.46, 0.2, 1.7]);
  });

  it("a rig with two hand bones and the head renamed Bone: 11 bones, depth 4, no head, no walk", async () => {
    const guard = { rig: { maxBones: 10, requiredBones: ["hips", "head"] }, animation: { requiredClips: ["walk"] } };
    const report = await caughtOnlyBy("figure-renamed.glb", guard, ["rig.maxBones", "rig.requiredBones", "animation.requiredClips"]);
    expect(report.measurements!.rig).toMatchObject({ bones: 11, depth: 4 });
    expect(measured(report, "rig.requiredBones")).toEqual({ found: 1, missing: ["head"], ambiguous: [] });
    expect(measured(report, "animation.requiredClips")).toEqual({ clips: ["stroll"], missing: ["walk"] });
  });

  it("a figure exported posed, the head turned 0.5 rad: its joint is 28.6479 degrees off the bind pose", async () => {
    const report = await caughtOnlyBy("figure-posed.glb", { skin: { restPose: true } }, ["skin.restPose"]);
    expect(measured(report, "skin.restPose")).toEqual({ method: "gltf", jointsOff: 1, joints: 9, maxOffset: 0, maxAngle: Math.round(((0.5 * 180) / Math.PI) * 1e4) / 1e4, offJoints: ["head"] });
  });

  it("the figure without its armature: no rig", async () => {
    const report = await caughtOnlyBy("figure-unrigged.glb", { rig: { required: true } }, ["rig.required"]);
    expect(measured(report, "rig.required")).toEqual({ armatures: 0, bones: 0 });
  });
});
