import { z } from "zod";

export const VIEWS = ["front", "back", "left", "right", "top", "bottom", "three-quarter"] as const;

export const count = z.number().int().nonnegative();
export const ratio = z.number().min(0).max(1);
export const length = z.number().nonnegative();

export const minNotOverMax = { message: "min must not exceed max" };
export const ordered = (value: { min?: number | undefined; max?: number | undefined }) => value.min === undefined || value.max === undefined || value.min <= value.max;

export const countRange = z.strictObject({ min: count.optional(), max: count.optional() }).refine(ordered, minNotOverMax);

const lengthRange = z
  .tuple([length, length])
  .refine(([low, high]) => low <= high, { message: "the first number (minimum) must not exceed the second (maximum)" });

export const sizeRule = z
  .strictObject({ x: lengthRange.optional(), y: lengthRange.optional(), z: lengthRange.optional(), minExtent: length.optional(), maxExtent: length.optional() })
  .refine((value) => value.minExtent === undefined || value.maxExtent === undefined || value.minExtent <= value.maxExtent, {
    message: "minExtent must not exceed maxExtent",
  });

export const point = z.tuple([z.number().finite(), z.number().finite(), z.number().finite()]);

export const glob = z
  .string()
  .min(1)
  .max(200)
  .regex(/^[^\x00-\x1f]+$/, { message: "a name pattern has no control characters" });

export const label = z
  .string()
  .min(1)
  .max(120)
  .regex(/^[^\x00-\x1f\x7f]+$/, { message: "a name has no control characters" });

export const distinct = (values: readonly string[]) => new Set(values).size === values.length;
