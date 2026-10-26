import { z } from "zod";
import { FORMATS } from "./spec.js";

const finite = z.number().finite();
const count = z.number().int().nonnegative();
const vector = z.tuple([finite, finite, finite]);

export const measurementsSchema = z.object({
  format: z.enum(FORMATS),
  fileBytes: count,
  triangles: count,
  objects: count,
  objectsAll: count,
  bounds: z.object({ min: vector, max: vector }),
  size: vector,
  origin: z.object({
    point: vector,
    source: z.string().max(200),
    bottomCentreDistance: finite,
    centreDistance: finite,
  }),
  manifold: z.object({
    nonManifoldEdges: count,
    boundaryEdges: count,
    wireEdges: count,
    nonManifoldVertices: count,
    looseVertices: count,
    looseParts: count,
  }),
  materials: z.object({ count, names: z.array(z.string().max(200)).max(64) }),
  uv: z.object({ present: z.boolean(), meshesWithoutUv: count, coverage: finite, overlap: finite }),
  externalFilesRefused: z.array(z.string().max(200)).max(1000),
});

export type Measurements = z.infer<typeof measurementsSchema>;

export const scriptErrorSchema = z.object({ code: z.string().max(64), message: z.string().max(2000) });

export const measureOutputSchema = z.union([
  z.object({
    ok: z.literal(true),
    measurements: measurementsSchema,
    limits: z.object({ memoryBytes: count, childProcesses: z.string().max(32), maxTriangles: count }),
  }),
  z.object({ ok: z.literal(false), error: scriptErrorSchema }),
]);

const deviceSchema = z.object({ backend: z.string().max(16), devices: z.array(z.string().max(200)).max(16) });
const elapsed = z.number().nonnegative();

export const probesSchema = z
  .array(z.object({ backend: z.string().max(16), devices: z.array(z.string().max(200)).max(16), usable: z.boolean(), reason: z.string().max(400) }))
  .max(8);

const scriptFailureSchema = z.object({ ok: z.literal(false), error: scriptErrorSchema, probes: probesSchema.optional() });

export const renderOutputSchema = z.union([
  z.object({
    ok: z.literal(true),
    views: z.array(z.object({ view: z.string().max(32), path: z.string() })),
    contactSheet: z.string(),
    contactSheetSize: z.tuple([count, count]),
    device: deviceSchema.nullable(),
    probes: probesSchema,
    timings: z.object({ device: elapsed.nullable(), views: elapsed.nullable(), sheet: elapsed }),
  }),
  scriptFailureSchema,
]);

export const closeupsOutputSchema = z.union([
  z.object({
    ok: z.literal(true),
    images: z.array(z.object({ name: z.string().max(64), path: z.string() })).max(16),
    sheet: z.string(),
    sheetSize: z.tuple([count, count]),
    device: deviceSchema,
    probes: probesSchema,
    timings: z.object({ device: elapsed.nullable(), render: elapsed, sheet: elapsed }),
  }),
  scriptFailureSchema,
]);
