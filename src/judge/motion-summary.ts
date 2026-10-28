import type { Measurements } from "./measurements.js";
import type { AnimationMeasurement, RigMeasurement, SkinMeasurement, VertexColorsMeasurement } from "./motion-measurements.js";
import { plainText, quoted } from "./untrusted.js";

const LISTED_CLIPS = 10;

function plural(count: number, word: string, words = `${word}s`): string {
  return `${count} ${count === 1 ? word : words}`;
}

function rigLine(rig: RigMeasurement): string {
  const roots = rig.roots.length > 0 ? `, roots ${rig.roots.map((root) => quoted(root)).join(", ")}` : "";
  const scheme = rig.scheme === undefined ? "" : `; bone map ${Object.keys(rig.scheme.matched).length} of ${rig.scheme.roles} roles matched`;
  return `  rig: ${plural(rig.armatures, "armature")}, ${plural(rig.bones, "bone")} (${rig.deformBones} deform), depth ${rig.depth}${roots}${scheme}`;
}

function restPoseText(skin: SkinMeasurement): string {
  const pose = skin.restPose;
  if (pose === null) return "no skin";
  if (pose.bound === null) return `rest pose not measured (${plainText(pose.reason ?? "unknown")})`;
  if (pose.bound) return `bound in rest pose (${pose.method}, ${plural(pose.joints, "joint")})`;
  return `not bound in rest pose: ${pose.jointsOff} of ${pose.joints} joints off (${pose.offJoints.map((joint) => quoted(joint)).join(", ")}), up to ${pose.maxOffset} m and ${pose.maxAngle} degrees`;
}

function skinLine(skin: SkinMeasurement): string {
  return `  skin: ${plural(skin.meshes, "skinned mesh", "skinned meshes")}, ${skin.vertices} vertices, at most ${skin.maxInfluences} influences, ${skin.unweighted} unweighted, ${skin.notNormalized} not normalized (tolerance ${skin.tolerance}); ${restPoseText(skin)}`;
}

function animationLines(animation: AnimationMeasurement): string[] {
  const size = animation.size === null ? "no geometry" : `${animation.size.map((value) => value.toFixed(3)).join(" x ")} m`;
  const lines = [`  animation: ${plural(animation.clips, "clip")}, size over every sampled frame ${size}`];
  for (const clip of animation.items.slice(0, LISTED_CLIPS)) {
    const rate = clip.frameRate === null ? "" : ` at ${clip.frameRate} fps`;
    const loop = clip.loopError === null ? "geometry changes between first and last frame" : `loop error ${clip.loopError} m`;
    lines.push(`    ${quoted(clip.name)}: ${clip.duration} s${rate}, ${clip.keyframes} keyframes, ${clip.samples} frames sampled, ${loop}, root motion ${clip.rootMotion.max} m`);
  }
  if (animation.clips > LISTED_CLIPS) lines.push(`    and ${animation.clips - LISTED_CLIPS} more in report.json`);
  if (animation.ignored.length > 0) lines.push(`    actions that animate nothing in the scene: ${animation.ignored.slice(0, LISTED_CLIPS).map((name) => quoted(name)).join(", ")}`);
  return lines;
}

function colourLine(colours: VertexColorsMeasurement): string {
  const { domains, types } = colours;
  return `  vertex colours: on ${colours.withColours} of ${plural(colours.meshes, "mesh", "meshes")}, ${plural(colours.attributes, "attribute")}: ${domains.corner} corner, ${domains.point} point; ${types.byte} byte, ${types.float} float`;
}

export function motionLines(measurements: Measurements): string[] {
  const lines: string[] = [];
  if (measurements.rig) lines.push(rigLine(measurements.rig));
  if (measurements.skin) lines.push(skinLine(measurements.skin));
  if (measurements.animation) lines.push(...animationLines(measurements.animation));
  if (measurements.vertexColors) lines.push(colourLine(measurements.vertexColors));
  return lines;
}
