import { z } from "zod";

const finite = z.number().finite();
const count = z.number().int().nonnegative();
const vector = z.tuple([finite, finite, finite]);
const name = z.string().max(200);
const bounds = z.object({ min: vector, max: vector });

export const MAX_BONE_NAMES = 2048;
export const MAX_CLIP_NAMES = 256;

export const boneSchemeSchema = z.object({
  roles: count,
  matched: z.record(name, name),
  missing: z.array(name).max(256),
  ambiguous: z.array(z.object({ name, bones: z.array(name).max(10) })).max(256),
  complete: z.boolean(),
});

export const rigSchema = z.object({
  armatures: count,
  bones: count,
  deformBones: count,
  depth: count,
  roots: z.array(name).max(64),
  boneNames: z.array(name).max(MAX_BONE_NAMES),
  items: z.array(z.object({ name, bones: count, deformBones: count, depth: count, roots: z.array(name).max(64) })).max(64),
  scheme: boneSchemeSchema.optional(),
});

export const restPoseSchema = z.object({
  method: z.enum(["gltf", "fbx", "blend", "obj"]),
  bound: z.boolean().nullable(),
  joints: count,
  jointsOff: count,
  maxOffset: finite,
  maxAngle: finite,
  maxScaleError: finite,
  offJoints: z.array(name).max(10),
  tolerance: z.object({ position: finite, angle: finite, scale: finite }),
  reason: z.string().max(300).nullable(),
});

export const skinSchema = z.object({
  meshes: count,
  vertices: count,
  maxInfluences: count,
  unweighted: count,
  notNormalized: count,
  tolerance: finite,
  restPose: restPoseSchema.nullable(),
  items: z
    .array(z.object({ object: name, armatures: z.array(name).max(64), vertices: count, maxInfluences: count, unweighted: count, notNormalized: count }))
    .max(64),
});

const clipSchema = z.object({
  name,
  duration: finite,
  frameRate: finite.nullable(),
  start: finite,
  end: finite,
  keyframes: count,
  keyTimes: count,
  channels: count,
  samples: count,
  candidates: count,
  loopError: finite.nullable(),
  rootMotion: z.object({ max: finite, horizontal: finite, vertical: finite }),
  bounds: bounds.nullable(),
  size: vector.nullable(),
});

export const animationSchema = z.object({
  clips: count,
  names: z.array(name).max(MAX_CLIP_NAMES),
  ignored: z.array(name).max(MAX_CLIP_NAMES),
  fps: finite,
  samplesPerClip: count,
  bounds: bounds.nullable(),
  size: vector.nullable(),
  items: z.array(clipSchema).max(MAX_CLIP_NAMES),
});

const attribute = z.object({ name, domain: z.string().max(16), type: z.string().max(16) });

export const vertexColorsSchema = z.object({
  meshes: count,
  withColours: count,
  attributes: count,
  domains: z.object({ point: count, corner: count }),
  types: z.object({ byte: count, float: count }),
  without: z.array(name).max(64),
  items: z.array(z.object({ mesh: name, attributes: z.array(attribute).max(64) })).max(64),
});

export const motionMeasurements = {
  rig: rigSchema.optional(),
  skin: skinSchema.optional(),
  animation: animationSchema.optional(),
  vertexColors: vertexColorsSchema.optional(),
};

export type RigMeasurement = z.infer<typeof rigSchema>;
export type SkinMeasurement = z.infer<typeof skinSchema>;
export type AnimationMeasurement = z.infer<typeof animationSchema>;
export type VertexColorsMeasurement = z.infer<typeof vertexColorsSchema>;
export type BoneScheme = z.infer<typeof boneSchemeSchema>;
