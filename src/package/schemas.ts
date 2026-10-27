import { z } from "zod";

const vector = z.tuple([z.number(), z.number(), z.number()]);
const bounds = z.object({ min: vector, max: vector });

const error = z.object({
  hausdorff: z.number().nonnegative(),
  hausdorffFraction: z.number().nonnegative(),
  mean: z.number().nonnegative(),
  referenceToCandidate: z.number().nonnegative(),
  candidateToReference: z.number().nonnegative(),
  samples: z.number().int().nonnegative(),
  diagonal: z.number().nonnegative(),
});

export const levelSchema = z.object({
  level: z.number().int().nonnegative(),
  names: z.array(z.string()),
  triangles: z.number().int().nonnegative(),
  ratio: z.number().nonnegative(),
  bounds,
  targetRatio: z.number().nullable().optional(),
  distance: z.number().positive().optional(),
  screenErrorPixels: z.number().nonnegative().optional(),
  maxScreenErrorPixels: z.number().nullable().optional(),
  error: error.optional(),
  modes: z.record(z.string(), z.number().int()).optional(),
  reduced: z.boolean().optional(),
  uvOverlap: z.number().nonnegative(),
});

export type Level = z.infer<typeof levelSchema>;

const failure = z.object({ code: z.string(), message: z.string() });

export const lodsOutputSchema = z.discriminatedUnion("ok", [
  z.object({
    ok: z.literal(true),
    stem: z.string(),
    layout: z.enum(["single", "separate"]),
    format: z.string(),
    diagonal: z.number(),
    radius: z.number(),
    levels: z.array(levelSchema).min(1),
    files: z.array(z.object({ level: z.number().int().nullable(), path: z.string() })).min(1),
    seconds: z.number(),
  }),
  z.object({ ok: z.literal(false), error: failure }),
]);

const viewResult = z.object({
  view: z.string(),
  lod0: z.string(),
  lod: z.string(),
  silhouetteIou: z.number(),
  similarity: z.number(),
  silhouettePixels: z.tuple([z.number().int(), z.number().int()]),
});

const renderedLevel = z.object({
  level: z.number().int(),
  distance: z.number(),
  crop: z.number().int(),
  views: z.array(viewResult),
  silhouetteIou: z.number(),
  similarity: z.number(),
  similarityMean: z.number(),
});

export type RenderedLevel = z.infer<typeof renderedLevel>;

export const packageRenderSchema = z.discriminatedUnion("ok", [
  z.object({
    ok: z.literal(true),
    device: z.object({ backend: z.string(), devices: z.array(z.string()) }).nullable(),
    probes: z.array(z.object({ backend: z.string(), devices: z.array(z.string()), usable: z.boolean(), reason: z.string() })).default([]),
    package: z.array(z.object({ level: z.number().int(), objects: z.number().int(), triangles: z.number().int(), bounds })),
    levels: z.array(renderedLevel),
    sheet: z.string().nullable(),
    sheetSize: z.tuple([z.number().int(), z.number().int()]).nullable(),
    samples: z.number().int(),
    timings: z.object({ device: z.number().nullable(), render: z.number() }),
  }),
  z.object({ ok: z.literal(false), error: failure, probes: z.array(z.object({ backend: z.string(), devices: z.array(z.string()), usable: z.boolean(), reason: z.string() })).optional() }),
]);

export type PackageRender = Extract<z.infer<typeof packageRenderSchema>, { ok: true }>;
