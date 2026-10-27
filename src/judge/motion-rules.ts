import type { Measurements } from "./measurements.js";
import type { AnimationMeasurement, BoneScheme, RigMeasurement, SkinMeasurement } from "./motion-measurements.js";
import { loopWanted, weightTolerance, type RigRule } from "./motion-spec.js";
import { globPattern } from "./object-rules.js";
import { sizeRules, upAxis, type RuleResult } from "./shape-rules.js";
import type { AssetSpec } from "./spec.js";

const LISTED = 10;

function listed(items: string[]): string[] {
  return items.length > LISTED ? [...items.slice(0, LISTED), `and ${items.length - LISTED} more`] : items;
}

function unmeasured(rule: string, limit: unknown): RuleResult {
  return { rule, measured: null, limit, pass: false };
}

function patterns(value: string | string[]): RegExp[] {
  return (Array.isArray(value) ? value : [value]).map(globPattern);
}

export function boneScheme(rig: RigMeasurement, rule: RigRule): BoneScheme {
  const complete = rig.boneNames.length === rig.bones;
  const wanted = rule.boneMap === undefined ? (rule.requiredBones ?? []) : Object.keys(rule.boneMap);
  const scheme: BoneScheme = { roles: wanted.length, matched: {}, missing: [], ambiguous: [], complete };
  for (const name of wanted) {
    const mapped = rule.boneMap?.[name];
    const found = mapped === undefined ? rig.boneNames.filter((bone) => bone === name) : rig.boneNames.filter((bone) => patterns(mapped).some((pattern) => pattern.test(bone)));
    if (found.length === 1) scheme.matched[name] = found[0]!;
    else if (found.length === 0) scheme.missing.push(name);
    else scheme.ambiguous.push({ name, bones: found.slice(0, LISTED) });
  }
  return scheme;
}

function rigRules(spec: AssetSpec, rig: RigMeasurement | undefined): RuleResult[] {
  const rule = spec.rig;
  if (rule === undefined) return [];
  const results: RuleResult[] = [];
  const presence = "an armature with at least one bone";
  if (rule.required === true) {
    results.push(rig === undefined ? unmeasured("rig.required", presence) : { rule: "rig.required", measured: { armatures: rig.armatures, bones: rig.bones }, limit: presence, pass: rig.armatures > 0 && rig.bones > 0 });
  }
  if (rule.maxBones !== undefined) results.push(rig === undefined ? unmeasured("rig.maxBones", rule.maxBones) : { rule: "rig.maxBones", measured: rig.bones, limit: rule.maxBones, pass: rig.bones <= rule.maxBones });
  if (rule.requiredBones !== undefined) {
    const limit = { bones: listed(rule.requiredBones), each: "matched by exactly one bone" };
    if (rig === undefined) return [...results, unmeasured("rig.requiredBones", limit)];
    const scheme = boneScheme(rig, rule);
    const missing = rule.requiredBones.filter((name) => scheme.missing.includes(name));
    const ambiguous = scheme.ambiguous.filter((entry) => rule.requiredBones!.includes(entry.name)).map((entry) => `${entry.name}: ${entry.bones.join(", ")}`);
    const measured = { found: rule.requiredBones.length - missing.length - ambiguous.length, missing: listed(missing), ambiguous: listed(ambiguous), ...(scheme.complete ? {} : { listed: `${rig.boneNames.length} of ${rig.bones} bones` }) };
    results.push({ rule: "rig.requiredBones", measured, limit, pass: scheme.complete && missing.length === 0 && ambiguous.length === 0 });
  }
  return results;
}

function skinRules(spec: AssetSpec, skin: SkinMeasurement | undefined): RuleResult[] {
  const rule = spec.skin;
  if (rule === undefined) return [];
  const wanted: [string, unknown, (skin: SkinMeasurement) => { measured: unknown; pass: boolean }][] = [];
  if (rule.maxInfluences !== undefined) {
    const limit = rule.maxInfluences;
    wanted.push(["skin.maxInfluences", limit, (measured) => ({ measured: measured.maxInfluences, pass: measured.maxInfluences <= limit })]);
  }
  if (rule.maxUnweighted !== undefined) {
    const limit = rule.maxUnweighted;
    wanted.push(["skin.maxUnweighted", limit, (measured) => ({ measured: measured.unweighted, pass: measured.unweighted <= limit })]);
  }
  if (rule.normalized !== undefined && rule.normalized !== false) {
    const tolerance = weightTolerance(rule);
    wanted.push([
      "skin.normalized",
      { notNormalized: 0, tolerance },
      (measured) => ({ measured: { notNormalized: measured.notNormalized, tolerance: measured.tolerance }, pass: measured.notNormalized === 0 && measured.tolerance === tolerance }),
    ]);
  }
  if (rule.restPose === true) {
    wanted.push([
      "skin.restPose",
      "every joint at its bind pose",
      (measured) => {
        const pose = measured.restPose;
        if (pose === null || pose.bound === null) return { measured: pose?.reason ?? "not measured", pass: false };
        const shown = { method: pose.method, jointsOff: pose.jointsOff, joints: pose.joints, maxOffset: pose.maxOffset, maxAngle: pose.maxAngle, offJoints: pose.offJoints };
        return { measured: shown, pass: pose.bound };
      },
    ]);
  }
  return wanted.map(([name, limit, check]) => {
    if (skin === undefined) return unmeasured(name, limit);
    if (skin.meshes === 0) return { rule: name, measured: "no skinned mesh", limit, pass: false };
    return { rule: name, limit, ...check(skin) };
  });
}

function clipNames(animation: AnimationMeasurement): string[] | null {
  return animation.names.length === animation.clips && animation.items.length === animation.clips ? animation.names : null;
}

function loopResult(spec: AssetSpec, animation: AnimationMeasurement): RuleResult | null {
  const loop = loopWanted(spec.animation);
  if (loop === null) return null;
  const limit = { clips: loop.clips === null ? "every clip" : listed(loop.clips), tolerance: loop.tolerance };
  const names = clipNames(animation);
  if (names === null) return { rule: "animation.loop", measured: `${animation.items.length} of ${animation.clips} clips listed`, limit, pass: false };
  const checked = loop.clips ?? names;
  const failing: string[] = [];
  const missing: string[] = [];
  for (const name of checked) {
    const clip = animation.items.find((item) => item.name === name);
    if (clip === undefined) missing.push(name);
    else if (clip.loopError === null) failing.push(`${name}: its geometry changes between the first and last frame`);
    else if (clip.loopError > loop.tolerance) failing.push(`${name}: ${clip.loopError} m`);
  }
  const measured = { checked: checked.length, failing: listed(failing), missing: listed(missing) };
  return { rule: "animation.loop", measured, limit, pass: checked.length > 0 && failing.length === 0 && missing.length === 0 };
}

function largest(animation: AnimationMeasurement, pick: (clip: AnimationMeasurement["items"][number]) => number): number {
  return Math.max(0, ...animation.items.map(pick));
}

function animationRules(spec: AssetSpec, animation: AnimationMeasurement | undefined): RuleResult[] {
  const rule = spec.animation;
  if (rule === undefined) return [];
  if (animation === undefined) return Object.keys(rule).map((name) => unmeasured(`animation.${name}`, rule[name as keyof typeof rule]));
  const results: RuleResult[] = [];
  const names = clipNames(animation);
  if (rule.requiredClips !== undefined) {
    const limit = listed(rule.requiredClips);
    const missing = names === null ? [] : rule.requiredClips.filter((name) => !names.includes(name));
    const measured = names === null ? `${animation.items.length} of ${animation.clips} clips listed` : { clips: listed(names), missing: listed(missing) };
    results.push({ rule: "animation.requiredClips", measured, limit, pass: names !== null && missing.length === 0 });
  }
  const loop = loopResult(spec, animation);
  if (loop !== null) results.push(loop);
  if (rule.maxDuration !== undefined) {
    const measured = largest(animation, (clip) => clip.duration);
    results.push({ rule: "animation.maxDuration", measured, limit: rule.maxDuration, pass: names !== null && measured <= rule.maxDuration });
  }
  if (rule.maxRootMotion !== undefined) {
    const measured = largest(animation, (clip) => clip.rootMotion.max);
    results.push({ rule: "animation.maxRootMotion", measured, limit: rule.maxRootMotion, pass: names !== null && measured <= rule.maxRootMotion });
  }
  if (rule.boundsWithin !== undefined) {
    const size = rule.boundsWithin === true ? spec.size : rule.boundsWithin;
    if (animation.size === null) results.push(unmeasured("animation.boundsWithin", size));
    else results.push(...sizeRules("animation.boundsWithin.", size, animation.size, upAxis(spec)));
  }
  return results;
}

function colourRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  const rule = spec.vertexColors;
  if (rule === undefined) return [];
  const colours = measurements.vertexColors;
  const results: RuleResult[] = [];
  if (rule.required === true) {
    const limit = "a colour attribute on every mesh";
    results.push(
      colours === undefined
        ? unmeasured("vertexColors.required", limit)
        : { rule: "vertexColors.required", measured: { meshes: colours.meshes, withColours: colours.withColours, without: listed(colours.without) }, limit, pass: colours.meshes > 0 && colours.withColours === colours.meshes },
    );
  }
  if (rule.domain !== undefined) {
    const wanted = rule.domain;
    const other = wanted === "point" ? "corner" : "point";
    results.push(
      colours === undefined
        ? unmeasured("vertexColors.domain", wanted)
        : { rule: "vertexColors.domain", measured: colours.attributes === 0 ? "no colour attributes" : colours.domains, limit: wanted, pass: colours.attributes > 0 && colours.domains[other] === 0 },
    );
  }
  return results;
}

export function motionRules(spec: AssetSpec, measurements: Measurements): RuleResult[] {
  return [...rigRules(spec, measurements.rig), ...skinRules(spec, measurements.skin), ...animationRules(spec, measurements.animation), ...colourRules(spec, measurements)];
}

export function motionExtras(spec: AssetSpec): string[] {
  const extras: string[] = [];
  if (spec.rig !== undefined) extras.push("rig");
  if (spec.skin !== undefined) extras.push("skin");
  if (spec.animation !== undefined) extras.push("animation");
  if (spec.vertexColors !== undefined) extras.push("colours");
  return extras;
}

export function withBoneScheme(spec: AssetSpec, measurements: Measurements): Measurements {
  const rule = spec.rig;
  if (rule?.boneMap === undefined || measurements.rig === undefined) return measurements;
  return { ...measurements, rig: { ...measurements.rig, scheme: boneScheme(measurements.rig, rule) } };
}
