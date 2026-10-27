import { readFileSync } from "node:fs";
import { z } from "zod";

export const FORMATS = ["glb", "gltf", "fbx", "obj", "blend"] as const;
export const VIEWS = ["front", "back", "left", "right", "top", "bottom", "three-quarter"] as const;
export const ORIGINS = ["bottom-centre", "centre"] as const;
export const DEFAULT_VIEWS = ["front", "back", "left", "right", "top", "three-quarter"] as const;
export const TEXTURE_KINDS = ["baseColor", "metallicRoughness", "normal", "emissive", "occlusion"] as const;
export const GLTF_FORMATS: readonly string[] = ["glb", "gltf"];
export const DEFAULT_FLOATING_TOLERANCE = 0.001;
export const MAX_FLOATING_TOLERANCE = 1;
export const UP_AXES = ["z", "y"] as const;
export const MAX_NAMED_OBJECTS = 64;

const count = z.number().int().nonnegative();
const ratio = z.number().min(0).max(1);
const length = z.number().nonnegative();

const minNotOverMax = { message: "min must not exceed max" };
const ordered = (value: { min?: number | undefined; max?: number | undefined }) => value.min === undefined || value.max === undefined || value.min <= value.max;

const countRange = z.strictObject({ min: count.optional(), max: count.optional() }).refine(ordered, minNotOverMax);

const triangleRange = z.strictObject({ min: count.optional(), max: count.optional(), minVisible: count.optional() }).refine(ordered, minNotOverMax);

const lengthRange = z
  .tuple([length, length])
  .refine(([low, high]) => low <= high, { message: "the first number (minimum) must not exceed the second (maximum)" });

const sizeRule = z
  .strictObject({ x: lengthRange.optional(), y: lengthRange.optional(), z: lengthRange.optional(), minExtent: length.optional(), maxExtent: length.optional() })
  .refine((value) => value.minExtent === undefined || value.maxExtent === undefined || value.minExtent <= value.maxExtent, {
    message: "minExtent must not exceed maxExtent",
  });

const point = z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]);

const originRule = z.union([z.enum(ORIGINS), z.strictObject({ point, tolerance: length })]);

const manifoldRule = z.union([z.boolean(), z.strictObject({ required: z.boolean().optional(), noInverted: z.boolean().optional() })]);

const glob = z
  .string()
  .min(1)
  .max(200)
  .regex(/^[^\x00-\x1f]+$/, { message: "a name pattern has no control characters" });

const namedObject = z.strictObject({
  name: glob,
  required: z.boolean().optional(),
  triangles: countRange.optional(),
  size: sizeRule.optional(),
  origin: originRule.optional(),
  materials: countRange.optional(),
});

const objectsRule = z
  .strictObject({ min: count.optional(), max: count.optional(), named: z.array(namedObject).min(1).max(MAX_NAMED_OBJECTS).optional() })
  .refine(ordered, minNotOverMax)
  .refine((value) => value.named === undefined || new Set(value.named.map((entry) => entry.name)).size === value.named.length, {
    message: "named object patterns must not repeat",
  });

const facesRule = z.strictObject({ maxDegenerate: count.optional(), maxDuplicate: count.optional(), maxHiddenRatio: ratio.optional() });

const pixels = z.number().int().positive();

const textures = z
  .strictObject({
    required: z
      .array(z.enum(TEXTURE_KINDS))
      .min(1)
      .refine((kinds) => new Set(kinds).size === kinds.length, { message: "map kinds must not repeat" })
      .optional(),
    minSize: pixels.optional(),
    maxSize: pixels.optional(),
    embedded: z.boolean().optional(),
    maxCount: count.optional(),
    maxGpuBytes: count.optional(),
    powerOfTwo: z.boolean().optional(),
  })
  .refine((value) => value.minSize === undefined || value.maxSize === undefined || value.minSize <= value.maxSize, {
    message: "minSize must not exceed maxSize",
  });

const gltf = z.strictObject({ validator: z.strictObject({ maxErrors: count.optional(), maxWarnings: count.optional() }) });

const parts = z.strictObject({ maxFloating: count, tolerance: length.max(MAX_FLOATING_TOLERANCE).optional() });

const baseSchema = z.strictObject({
  $schema: z.string().optional(),
  name: z.string().min(1).max(200).optional(),
  format: z.enum(FORMATS),
  upAxis: z.enum(UP_AXES).optional(),
  triangles: triangleRange.optional(),
  size: sizeRule.optional(),
  origin: originRule.optional(),
  manifold: manifoldRule.optional(),
  faces: facesRule.optional(),
  shells: z.strictObject({ max: count }).optional(),
  materials: countRange.optional(),
  uv: z.strictObject({ required: z.boolean().optional(), maxOverlap: ratio.optional(), minCoverage: ratio.optional() }).optional(),
  objects: objectsRule.optional(),
  fileSize: z.strictObject({ maxBytes: z.number().int().positive() }).optional(),
  selfContained: z.boolean().optional(),
  renders: z.strictObject({ required: z.boolean() }).optional(),
  views: z
    .array(z.enum(VIEWS))
    .min(1)
    .refine((views) => new Set(views).size === views.length, { message: "views must not repeat" })
    .optional(),
  brief: z.string().max(4000).optional(),
  textures: textures.optional(),
  gltf: gltf.optional(),
  parts: parts.optional(),
});

export const assetSpecSchema = baseSchema.refine((spec) => spec.gltf === undefined || GLTF_FORMATS.includes(spec.format), {
  message: "the gltf rules need format glb or gltf",
  path: ["gltf"],
});

export type AssetSpec = z.infer<typeof assetSpecSchema>;
export type NamedObject = z.infer<typeof namedObject>;
export type SizeRule = z.infer<typeof sizeRule>;
export type OriginRule = z.infer<typeof originRule>;

export class SpecError extends Error {
  constructor(readonly problems: string[]) {
    super(`invalid asset spec:\n${problems.map((problem) => `  - ${problem}`).join("\n")}`);
    this.name = "SpecError";
  }
}

function describeIssue(issue: z.core.$ZodIssue): string {
  const where = issue.path.length > 0 ? issue.path.map(String).join(".") : "spec";
  return `${where}: ${issue.message}`;
}

export function parseSpec(value: unknown): AssetSpec {
  const result = assetSpecSchema.safeParse(value);
  if (!result.success) throw new SpecError(result.error.issues.map(describeIssue));
  return result.data;
}

export function readSpec(path: string): AssetSpec {
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch {
    throw new SpecError([`cannot read the spec file ${path}`]);
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new SpecError([`the spec is not valid JSON: ${(error as Error).message}`]);
  }
  return parseSpec(value);
}

export function specJsonSchema(): Record<string, unknown> {
  return {
    title: "Blendworks asset spec",
    description: "Rules a delivered 3D asset must meet. Every rule is optional except format; lengths are in metres.",
    ...z.toJSONSchema(assetSpecSchema, { target: "draft-2020-12" }),
  };
}
