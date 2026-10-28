import { describe, expect, it } from "vitest";
import type { Measurements } from "../../src/judge/measurements.js";
import type { AnimationMeasurement, RigMeasurement, SkinMeasurement, VertexColorsMeasurement } from "../../src/judge/motion-measurements.js";
import { boneScheme, motionExtras, withBoneScheme } from "../../src/judge/motion-rules.js";
import { summarize } from "../../src/judge/report.js";
import { evaluateRules } from "../../src/judge/rules.js";
import { parseSpec, SpecError } from "../../src/judge/spec.js";
import { assetRecord, CRATE_MEASUREMENTS } from "./measured.js";

const BONES = ["arm.L", "arm.R", "head", "hips", "shin.L", "shin.R", "spine", "thigh.L", "thigh.R"];

const RIG: RigMeasurement = {
  armatures: 1,
  bones: 9,
  deformBones: 9,
  depth: 3,
  roots: ["hips"],
  boneNames: BONES,
  items: [{ name: "Figure", bones: 9, deformBones: 9, depth: 3, roots: ["hips"] }],
};

const REST = { method: "gltf" as const, bound: true, joints: 9, jointsOff: 0, maxOffset: 0, maxAngle: 0, maxScaleError: 0, offJoints: [], tolerance: { position: 0.0001, angle: 0.01, scale: 0.0001 }, reason: null };

const SKIN: SkinMeasurement = {
  meshes: 1,
  vertices: 56,
  maxInfluences: 2,
  unweighted: 0,
  notNormalized: 0,
  tolerance: 0.01,
  restPose: REST,
  items: [{ object: "Body", armatures: ["Figure"], vertices: 56, maxInfluences: 2, unweighted: 0, notNormalized: 0 }],
};

const WALK = {
  name: "walk",
  duration: 1,
  frameRate: 24,
  start: 1,
  end: 25,
  keyframes: 16,
  keyTimes: 4,
  channels: 4,
  samples: 25,
  candidates: 25,
  loopError: 0,
  rootMotion: { max: 0, horizontal: 0, vertical: 0 },
  bounds: { min: [-0.23, -0.39653, -0.001334], max: [0.23, 0.39653, 1.7] } as { min: [number, number, number]; max: [number, number, number] },
  size: [0.46, 0.79306, 1.701334] as [number, number, number],
};

const ANIMATION: AnimationMeasurement = { clips: 1, names: ["walk"], ignored: [], fps: 24, samplesPerClip: 240, bounds: WALK.bounds, size: WALK.size, items: [WALK] };

const COLOURS: VertexColorsMeasurement = {
  meshes: 2,
  withColours: 2,
  attributes: 2,
  domains: { point: 0, corner: 2 },
  types: { byte: 2, float: 0 },
  without: [],
  items: [
    { mesh: "Painted", attributes: [{ name: "Color", domain: "corner", type: "byte" }] },
    { mesh: "Trim", attributes: [{ name: "Color", domain: "corner", type: "byte" }] },
  ],
};

const FIGURE: Measurements = { ...CRATE_MEASUREMENTS, size: [0.46, 0.2, 1.7], rig: RIG, skin: SKIN, animation: ANIMATION, vertexColors: COLOURS };

const SPEC = {
  format: "glb",
  size: { x: [0.4, 0.5], y: [0.1, 0.9], z: [1.6, 1.75] },
  rig: { required: true, maxBones: 9, requiredBones: ["hips", "head", "thigh.L"] },
  skin: { maxInfluences: 4, maxUnweighted: 0, normalized: true, restPose: true },
  animation: { requiredClips: ["walk"], loop: true, maxDuration: 1, maxRootMotion: 0.05, boundsWithin: true },
  vertexColors: { required: true, domain: "corner" },
};

const MOTION_RULES = [
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
  "vertexColors.required",
  "vertexColors.domain",
];

function judged(measurements: Measurements, overrides: Record<string, unknown> = {}) {
  return evaluateRules(parseSpec({ ...SPEC, ...overrides }), measurements);
}

function failing(measurements: Measurements, overrides: Record<string, unknown> = {}): string[] {
  return judged(measurements, overrides)
    .filter((rule) => !rule.pass)
    .map((rule) => rule.rule);
}

function problems(value: unknown): string[] {
  try {
    parseSpec(value);
  } catch (error) {
    if (error instanceof SpecError) return error.problems;
    throw error;
  }
  return [];
}

describe("the rig, skin, animation and vertex colour rules", () => {
  it("pass on the measured figure, after the older rules, in a fixed order", () => {
    const rules = judged(FIGURE);
    expect(rules.map((rule) => rule.rule)).toEqual(["format", "size.x", "size.y", "size.z", ...MOTION_RULES]);
    expect(rules.filter((rule) => !rule.pass)).toEqual([]);
  });

  it("include both ends of each limit", () => {
    expect(failing({ ...FIGURE, rig: { ...RIG, bones: 10, boneNames: [...BONES, "tail"] } })).toEqual(["rig.maxBones"]);
    expect(failing({ ...FIGURE, skin: { ...SKIN, maxInfluences: 4 } })).toEqual([]);
    expect(failing({ ...FIGURE, skin: { ...SKIN, maxInfluences: 5 } })).toEqual(["skin.maxInfluences"]);
    expect(failing({ ...FIGURE, skin: { ...SKIN, unweighted: 8 } })).toEqual(["skin.maxUnweighted"]);
    expect(failing({ ...FIGURE, skin: { ...SKIN, unweighted: 8 } }, { skin: { maxUnweighted: 8 } })).toEqual([]);
    expect(failing({ ...FIGURE, skin: { ...SKIN, notNormalized: 4 } })).toEqual(["skin.normalized"]);
    expect(failing({ ...FIGURE, animation: { ...ANIMATION, items: [{ ...WALK, duration: 1.000001 }] } })).toEqual(["animation.maxDuration"]);
    expect(failing({ ...FIGURE, animation: { ...ANIMATION, items: [{ ...WALK, rootMotion: { max: 1, horizontal: 1, vertical: 0 } }] } })).toEqual(["animation.maxRootMotion"]);
  });

  it("require an armature with bones, and find required bones by exact name", () => {
    const none: RigMeasurement = { armatures: 0, bones: 0, deformBones: 0, depth: 0, roots: [], boneNames: [], items: [] };
    expect(failing({ ...FIGURE, rig: none })).toEqual(["rig.required", "rig.requiredBones"]);
    const renamed = { ...RIG, boneNames: BONES.map((bone) => (bone === "head" ? "Bone" : bone)) };
    const rule = judged({ ...FIGURE, rig: renamed }).find((entry) => entry.rule === "rig.requiredBones");
    expect(rule).toEqual({ rule: "rig.requiredBones", measured: { found: 2, missing: ["head"], ambiguous: [] }, limit: { bones: ["hips", "head", "thigh.L"], each: "matched by exactly one bone" }, pass: false });
  });

  it("match bone roles through a bone map: one bone per role, never two", () => {
    const map = { hips: "hips", head: ["Head", "head"], leftLeg: "thigh.L", arm: "arm.?" };
    const scheme = boneScheme(RIG, { boneMap: map, requiredBones: ["hips"] });
    expect(scheme).toEqual({ roles: 4, matched: { hips: "hips", head: "head", leftLeg: "thigh.L" }, missing: [], ambiguous: [{ name: "arm", bones: ["arm.L", "arm.R"] }], complete: true });
    expect(failing(FIGURE, { rig: { boneMap: map, requiredBones: ["hips", "leftLeg"] } })).toEqual([]);
    const both = judged(FIGURE, { rig: { boneMap: map, requiredBones: ["hips", "arm"] } }).find((entry) => entry.rule === "rig.requiredBones");
    expect(both?.measured).toEqual({ found: 1, missing: [], ambiguous: ["arm: arm.L, arm.R"] });
    expect(both?.pass).toBe(false);
    expect(withBoneScheme(parseSpec({ ...SPEC, rig: { boneMap: map } }), FIGURE).rig?.scheme?.matched).toEqual({ hips: "hips", head: "head", leftLeg: "thigh.L" });
    expect(withBoneScheme(parseSpec(SPEC), FIGURE)).toBe(FIGURE);
  });

  it("fail a bone lookup when not every bone name was listed", () => {
    const rule = judged({ ...FIGURE, rig: { ...RIG, bones: 3000 } }).find((entry) => entry.rule === "rig.requiredBones");
    expect(rule?.pass).toBe(false);
    expect(rule?.measured).toMatchObject({ listed: "9 of 3000 bones" });
  });

  it("fail every skin rule when nothing is skinned", () => {
    const bare: SkinMeasurement = { ...SKIN, meshes: 0, vertices: 0, maxInfluences: 0, restPose: null, items: [] };
    const rules = judged({ ...FIGURE, skin: bare }).filter((rule) => rule.rule.startsWith("skin."));
    expect(rules.map((rule) => [rule.rule, rule.measured, rule.pass])).toEqual(["skin.maxInfluences", "skin.maxUnweighted", "skin.normalized", "skin.restPose"].map((rule) => [rule, "no skinned mesh", false]));
  });

  it("check the weight sum with the tolerance the spec gives, 0.01 when left out", () => {
    expect(judged(FIGURE).find((rule) => rule.rule === "skin.normalized")?.limit).toEqual({ notNormalized: 0, tolerance: 0.01 });
    expect(failing(FIGURE, { skin: { normalized: { tolerance: 0.2 } } })).toEqual(["skin.normalized"]);
    expect(failing({ ...FIGURE, skin: { ...SKIN, tolerance: 0.2 } }, { skin: { normalized: { tolerance: 0.2 } } })).toEqual([]);
    expect(failing(FIGURE, { skin: { normalized: false } })).toEqual([]);
  });

  it("fail the rest pose when a joint is off its bind pose or the bind cannot be read", () => {
    const turned = { ...REST, bound: false, jointsOff: 1, maxAngle: 28.6479, offJoints: ["head"] };
    const rule = judged({ ...FIGURE, skin: { ...SKIN, restPose: turned } }).find((entry) => entry.rule === "skin.restPose");
    expect(rule).toEqual({
      rule: "skin.restPose",
      measured: { method: "gltf", jointsOff: 1, joints: 9, maxOffset: 0, maxAngle: 28.6479, offJoints: ["head"] },
      limit: "every joint at its bind pose",
      pass: false,
    });
    const unread = { ...REST, bound: null, reason: "the inverse bind matrices are not a plain float MAT4 accessor" };
    expect(judged({ ...FIGURE, skin: { ...SKIN, restPose: unread } }).find((entry) => entry.rule === "skin.restPose")).toMatchObject({ measured: unread.reason, pass: false });
  });

  it("check loops within 1 mm, or the spec's tolerance, on every clip or the named ones", () => {
    const open = { ...ANIMATION, items: [{ ...WALK, loopError: 0.179977 }] };
    expect(judged({ ...FIGURE, animation: open }).find((rule) => rule.rule === "animation.loop")).toEqual({
      rule: "animation.loop",
      measured: { checked: 1, failing: ["walk: 0.179977 m"], missing: [] },
      limit: { clips: "every clip", tolerance: 0.001 },
      pass: false,
    });
    expect(failing({ ...FIGURE, animation: { ...ANIMATION, items: [{ ...WALK, loopError: 0.001 }] } })).toEqual([]);
    expect(failing({ ...FIGURE, animation: open }, { animation: { loop: { tolerance: 0.18 } } })).toEqual([]);
    expect(failing({ ...FIGURE, animation: open }, { animation: { loop: false } })).toEqual([]);
    expect(failing(FIGURE, { animation: { loop: { clips: ["walk", "run"] } } })).toEqual(["animation.loop"]);
    expect(failing({ ...FIGURE, animation: { ...ANIMATION, items: [{ ...WALK, loopError: null }] } })).toEqual(["animation.loop"]);
    const still = { ...ANIMATION, clips: 0, names: [], items: [] };
    expect(failing({ ...FIGURE, animation: still })).toEqual(["animation.requiredClips", "animation.loop"]);
  });

  it("apply the size rule to the bounds over every sampled frame", () => {
    const drifting = { ...ANIMATION, size: [0.46, 1.543059, 1.701332] as [number, number, number] };
    expect(failing({ ...FIGURE, animation: drifting })).toEqual(["animation.boundsWithin.size.y"]);
    expect(failing({ ...FIGURE, animation: drifting }, { animation: { boundsWithin: { maxExtent: 1.75 } } })).toEqual([]);
    expect(failing({ ...FIGURE, animation: drifting }, { animation: { boundsWithin: { maxExtent: 1.5 } } })).toEqual(["animation.boundsWithin.size.maxExtent"]);
    expect(failing({ ...FIGURE, animation: drifting }, { upAxis: "y", size: undefined, animation: { boundsWithin: { z: [0, 1.6] } } })).toEqual([]);
  });

  it("need colours on every mesh, in the domain the spec names", () => {
    const partly = { ...COLOURS, withColours: 1, attributes: 1, domains: { point: 0, corner: 1 }, without: ["Trim"] };
    expect(failing({ ...FIGURE, vertexColors: partly })).toEqual(["vertexColors.required"]);
    const points = { ...COLOURS, domains: { point: 2, corner: 0 }, types: { byte: 0, float: 2 } };
    expect(failing({ ...FIGURE, vertexColors: points })).toEqual(["vertexColors.domain"]);
    expect(failing({ ...FIGURE, vertexColors: points }, { vertexColors: { domain: "point" } })).toEqual([]);
    const bare = { ...COLOURS, withColours: 0, attributes: 0, domains: { point: 0, corner: 0 }, without: ["Painted", "Trim"] };
    expect(judged({ ...FIGURE, vertexColors: bare }).filter((rule) => !rule.pass).map((rule) => [rule.rule, rule.measured])).toEqual([
      ["vertexColors.required", { meshes: 2, withColours: 0, without: ["Painted", "Trim"] }],
      ["vertexColors.domain", "no colour attributes"],
    ]);
  });

  it("fail, never pass, a rule whose measurement is missing", () => {
    const rules = judged(CRATE_MEASUREMENTS);
    expect(rules.filter((rule) => MOTION_RULES.includes(rule.rule) || rule.rule.startsWith("animation."))).toSatisfy((found: { pass: boolean; measured: unknown }[]) => found.length > 0 && found.every((rule) => !rule.pass && rule.measured === null));
  });

  it("ask the measuring script only for what the spec checks", () => {
    expect(motionExtras(parseSpec({ format: "glb" }))).toEqual([]);
    expect(motionExtras(parseSpec(SPEC))).toEqual(["rig", "skin", "animation", "colours"]);
    expect(motionExtras(parseSpec({ format: "obj", vertexColors: { required: true } }))).toEqual(["colours"]);
  });

  it("summarise the rig, the skin, every clip and the colours", () => {
    const rules = judged(FIGURE);
    const text = summarize({
      passed: true,
      preview: true,
      spec: { path: "figure.spec.json", sha256: null, name: "figure" },
      asset: assetRecord("figure.glb"),
      blender: null,
      sandbox: null,
      renderSandbox: null,
      device: null,
      failure: null,
      rules,
      measurements: FIGURE,
      renders: null,
      timings: { measure: null, device: null, render: null, sheet: null, total: 1 },
    });
    expect(text).toContain("  rig: 1 armature, 9 bones (9 deform), depth 3, roots \"hips\"");
    expect(text).toContain("  skin: 1 skinned mesh, 56 vertices, at most 2 influences, 0 unweighted, 0 not normalized (tolerance 0.01); bound in rest pose (gltf, 9 joints)");
    expect(text).toContain("  animation: 1 clip, size over every sampled frame 0.460 x 0.793 x 1.701 m");
    expect(text).toContain("    \"walk\": 1 s at 24 fps, 16 keyframes, 25 frames sampled, loop error 0 m, root motion 0 m");
    expect(text).toContain("  vertex colours: on 2 of 2 meshes, 2 attributes: 2 corner, 0 point; 2 byte, 0 float");
    expect(text).toContain("  pass  animation.boundsWithin.size.y  measured 0.79306; required between [0.1, 0.9]");
  });
});

describe("the spec groups for rigs, animation, colours and references", () => {
  it("accept the full example and keep it as written", () => {
    expect(parseSpec(SPEC)).toEqual(SPEC);
  });

  it("refuse animation rules for formats whose animation the judge does not read", () => {
    expect(problems({ format: "fbx", animation: { maxDuration: 1 } })).toEqual(["animation: the animation rules need format glb, gltf, blend: the judge reads no FBX or OBJ animation"]);
    expect(problems({ format: "fbx", rig: { required: true }, skin: { maxInfluences: 4 } })).toEqual([]);
  });

  it("refuse rig, skin and animation rules beside lods or package, which refuse skinned meshes", () => {
    const expected = ["lods: rig, skin and animation rules cannot be combined with lods or package: packaging refuses skinned meshes and shape keys"];
    expect(problems({ format: "glb", skin: { maxInfluences: 4 }, package: { meshopt: true } })).toEqual(expected);
    expect(problems({ format: "glb", rig: { required: true }, lods: { count: 1, ratios: [0.5] } })).toEqual(expected);
    expect(problems({ format: "glb", vertexColors: { required: true }, package: { meshopt: true } })).toEqual([]);
  });

  it("need size for boundsWithin true, roles of the map for required bones, and no repeats", () => {
    expect(problems({ format: "glb", animation: { boundsWithin: true } })).toEqual(["animation.boundsWithin: animation.boundsWithin true applies the size rule, so it needs size"]);
    expect(problems({ format: "glb", rig: { boneMap: { hips: "Hips" }, requiredBones: ["hips", "head"] } })).toEqual(["rig.requiredBones: with a boneMap, every required bone is a role of the map"]);
    expect(problems({ format: "glb", rig: { requiredBones: ["hips", "hips"] } })).toEqual(["rig.requiredBones: required bones must not repeat"]);
    expect(problems({ format: "glb", animation: { requiredClips: [] } }).length).toBe(1);
    expect(problems({ format: "glb", skin: { maxInfluences: 0 } }).length).toBe(1);
    expect(problems({ format: "glb", skin: { normalized: { tolerance: 0 } } }).length).toBe(1);
    expect(problems({ format: "glb", rig: { boneMap: { "1st": "x" } } }).length).toBe(1);
    expect(problems({ format: "glb", vertexColors: { domain: "face" } }).length).toBe(1);
    expect(problems({ format: "glb", animation: { loop: { tolerance: 2 } } }).length).toBe(1);
  });

  it("refuse reference masks that are not plain relative PNG paths, and references without views", () => {
    const sha256 = "0".repeat(64);
    const view = (mask: string) => ({ format: "glb", reference: { views: { front: { sha256, mask } } } });
    expect(problems(view("masks/front.png"))).toEqual([]);
    for (const mask of ["/etc/front.png", "C:/front.png", "../front.png", "masks/../../front.png", "masks\\front.png", "front.jpg", "./front.png", "front.png:stream", "a//front.png"]) {
      expect(problems(view(mask)), mask).toHaveLength(1);
    }
    expect(problems({ format: "glb", reference: { views: {} } })).toEqual(["reference.views: a reference needs at least one view"]);
    expect(problems({ format: "glb", reference: { views: { side: { sha256, mask: "a.png" } } } })).toContain('reference.views: Unrecognized key: "side"');
    expect(problems({ format: "glb", reference: { views: { front: { sha256: "ABC", mask: "a.png" } } } })).toHaveLength(1);
    expect(problems({ format: "glb", reference: { views: { front: { sha256, mask: "a.png" }, top: { sha256, mask: "a.png" } } } })).toEqual(["reference.views: each view needs its own mask file"]);
    expect(problems({ format: "glb", reference: { views: { front: { sha256, mask: "a.png" } }, bounds: { min: [0, 0, 1], max: [1, 1, 0] } } })).toHaveLength(1);
  });
});
