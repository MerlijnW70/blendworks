import { z } from "zod";
import { count, distinct, glob, label, length, sizeRule } from "./spec-shapes.js";

export const MOTION_FORMATS: readonly string[] = ["glb", "gltf", "blend"];
export const MAX_REQUIRED_BONES = 256;
export const MAX_BONE_ROLES = 256;
export const MAX_ROLE_PATTERNS = 16;
export const MAX_CLIPS = 64;
export const DEFAULT_WEIGHT_TOLERANCE = 0.01;
export const MAX_WEIGHT_TOLERANCE = 0.5;
export const DEFAULT_LOOP_TOLERANCE = 0.001;
export const MAX_LOOP_TOLERANCE = 1;
export const COLOUR_DOMAINS = ["point", "corner"] as const;

const role = z.string().regex(/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/, { message: "a role is a letter, then up to 63 letters, digits, dots, dashes or underscores" });

const names = (max: number, what: string) =>
  z
    .array(label)
    .min(1)
    .max(max)
    .refine(distinct, { message: `${what} must not repeat` });

const boneMap = z
  .record(role, z.union([glob, z.array(glob).min(1).max(MAX_ROLE_PATTERNS)]))
  .refine((map) => Object.keys(map).length >= 1 && Object.keys(map).length <= MAX_BONE_ROLES, { message: `a bone map has 1 to ${MAX_BONE_ROLES} roles` });

export const rigRule = z
  .strictObject({
    required: z.boolean().optional(),
    maxBones: count.optional(),
    requiredBones: names(MAX_REQUIRED_BONES, "required bones").optional(),
    boneMap: boneMap.optional(),
  })
  .refine((rig) => rig.boneMap === undefined || rig.requiredBones === undefined || rig.requiredBones.every((name) => Object.hasOwn(rig.boneMap!, name)), {
    message: "with a boneMap, every required bone is a role of the map",
    path: ["requiredBones"],
  });

export const skinRule = z.strictObject({
  maxInfluences: z.number().int().min(1).optional(),
  maxUnweighted: count.optional(),
  normalized: z.union([z.boolean(), z.strictObject({ tolerance: z.number().gt(0).max(MAX_WEIGHT_TOLERANCE) })]).optional(),
  restPose: z.boolean().optional(),
});

const loopRule = z.union([
  z.boolean(),
  z.strictObject({ clips: names(MAX_CLIPS, "loop clips").optional(), tolerance: length.max(MAX_LOOP_TOLERANCE).optional() }),
]);

export const animationRule = z.strictObject({
  requiredClips: names(MAX_CLIPS, "required clips").optional(),
  loop: loopRule.optional(),
  maxDuration: z.number().positive().optional(),
  maxRootMotion: length.optional(),
  boundsWithin: z.union([z.literal(true), sizeRule]).optional(),
});

export const vertexColorsRule = z.strictObject({ required: z.boolean().optional(), domain: z.enum(COLOUR_DOMAINS).optional() });

export type RigRule = z.infer<typeof rigRule>;
export type SkinRule = z.infer<typeof skinRule>;
export type AnimationRule = z.infer<typeof animationRule>;
export type VertexColorsRule = z.infer<typeof vertexColorsRule>;

export function weightTolerance(skin: SkinRule | undefined): number {
  return typeof skin?.normalized === "object" ? skin.normalized.tolerance : DEFAULT_WEIGHT_TOLERANCE;
}

export function loopWanted(animation: AnimationRule | undefined): { clips: string[] | null; tolerance: number } | null {
  const loop = animation?.loop;
  if (loop === undefined || loop === false) return null;
  if (loop === true) return { clips: null, tolerance: DEFAULT_LOOP_TOLERANCE };
  return { clips: loop.clips ?? null, tolerance: loop.tolerance ?? DEFAULT_LOOP_TOLERANCE };
}
