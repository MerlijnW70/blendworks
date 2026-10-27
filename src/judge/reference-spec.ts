import { z } from "zod";
import { point, ratio, VIEWS } from "./spec-shapes.js";

export const MAX_MASK_PATH = 200;

const sha256 = z.string().regex(/^[0-9a-f]{64}$/, { message: "a sha256 is 64 lower-case hexadecimal digits" });

export function maskPathProblem(path: string): string | null {
  if (/[\x00-\x1f\x7f]/.test(path)) return "has control characters";
  if (path.includes("\\")) return "uses a backslash; separate folders with /";
  if (path.startsWith("/") || /^[A-Za-z]:/.test(path) || path.includes(":")) return "is absolute or names a scheme or drive";
  if (path.split("/").some((part) => part === ".." || part === "." || part === "")) return "has an empty, . or .. segment";
  if (!/\.png$/i.test(path)) return "is not a .png file";
  return null;
}

const maskPath = z
  .string()
  .min(1)
  .max(MAX_MASK_PATH)
  .superRefine((path, context) => {
    const problem = maskPathProblem(path);
    if (problem !== null) context.addIssue({ code: "custom", message: `the mask path ${problem}` });
  });

const limits = { minIoU: ratio.optional(), maxBoundaryDistance: ratio.optional() };

const referenceView = z.strictObject({ sha256, mask: maskPath, ...limits });

const box = z
  .strictObject({ min: point, max: point })
  .refine((value) => value.min.every((low, axis) => low <= (value.max[axis] ?? low)), { message: "every min must not exceed its max" });

export const referenceRule = z
  .strictObject({ views: z.partialRecord(z.enum(VIEWS), referenceView), bounds: box.optional(), ...limits })
  .refine((value) => Object.keys(value.views).length >= 1, { message: "a reference needs at least one view", path: ["views"] })
  .refine((value) => new Set(Object.values(value.views).map((view) => view?.mask)).size === Object.keys(value.views).length, {
    message: "each view needs its own mask file",
    path: ["views"],
  });

export type ReferenceRule = z.infer<typeof referenceRule>;
export type ReferenceView = z.infer<typeof referenceView>;
