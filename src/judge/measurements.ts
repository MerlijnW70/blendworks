import { z } from "zod";
import { FORMATS, TEXTURE_KINDS } from "./spec.js";

const finite = z.number().finite();
const count = z.number().int().nonnegative();
const vector = z.tuple([finite, finite, finite]);
const name = z.string().max(200);
const names = z.object({ count, names: z.array(name).max(64) });
const kinds = z.array(z.enum(TEXTURE_KINDS)).max(TEXTURE_KINDS.length);

export const texturesSchema = z.object({
  count,
  gpuBytes: count,
  smallestSide: count.nullable(),
  largestSide: count.nullable(),
  images: z
    .array(
      z.object({
        name,
        kinds,
        materials: z.array(name).max(64),
        width: count,
        height: count,
        colourSpace: z.string().max(64),
        embedded: z.boolean(),
        source: z.enum(["packed", "generated", "file"]),
        file: name.nullable(),
        gpuBytes: count,
        powerOfTwo: z.boolean(),
      }),
    )
    .max(256),
  materials: z.array(z.object({ name, maps: kinds })).max(256),
  facesWithoutMaterial: z.boolean(),
  missing: z.object(Object.fromEntries(TEXTURE_KINDS.map((kind) => [kind, names])) as Record<(typeof TEXTURE_KINDS)[number], typeof names>),
  external: names,
  nonPowerOfTwo: names,
  colourSpaceMismatches: z.object({
    count,
    items: z.array(z.object({ image: name, kind: z.enum(TEXTURE_KINDS), colourSpace: z.string().max(64), expected: z.string().max(64) })).max(64),
  }),
});

export const floatingSchema = z.object({
  tolerance: finite,
  parts: count,
  count,
  items: z.array(z.object({ object: name, index: count, bounds: z.object({ min: vector, max: vector }) })).max(64),
});

const bounds = z.object({ min: vector, max: vector });

export const objectListSchema = z.object({
  count,
  items: z
    .array(
      z.object({
        name,
        instances: count,
        triangles: count,
        bounds,
        size: vector,
        origin: z.object({ point: vector, bottomCentreDistance: finite, centreDistance: finite }),
        materials: z.array(name).max(64),
      }),
    )
    .max(1024),
});

export const referencesSchema = z.object({ files: count, unresolved: z.array(z.string().max(400)).max(1000) });

const measured = {
  triangles: count,
  visibleTriangles: count,
  objects: count,
  objectsAll: count,
  bounds,
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
  shells: z.object({ count, closed: count, inverted: count }),
  faces: z.object({ degenerate: count, duplicate: count, hiddenRatio: z.number().min(0).max(1), hiddenFaces: count, tested: count, sampled: z.boolean() }),
  materials: z.object({ count, names: z.array(z.string().max(200)).max(64) }),
  uv: z.object({ present: z.boolean(), meshesWithoutUv: count, coverage: finite, overlap: finite, outsideUnitSquare: finite }),
  unitScale: z.number().positive().finite(),
  externalFilesRefused: z.array(z.string().max(200)).max(1000),
};

const optional = { textures: texturesSchema.optional(), floating: floatingSchema.optional(), objectList: objectListSchema.optional() };

export const scriptMeasurementsSchema = z.object({ format: z.enum(FORMATS), ...measured, ...optional });

export const measurementsSchema = z.object({ format: z.enum(FORMATS), fileBytes: count, ...measured, references: referencesSchema, ...optional });

export type Measurements = z.infer<typeof measurementsSchema>;

export const scriptErrorSchema = z.object({ code: z.string().max(64), message: z.string().max(2000) });

export const measureOutputSchema = z.union([
  z.object({
    ok: z.literal(true),
    measurements: scriptMeasurementsSchema,
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
