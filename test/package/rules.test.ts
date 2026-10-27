import { describe, expect, it } from "vitest";
import { parseSpec, SpecError } from "../../src/judge/spec.js";
import type { PackageFile, PackageReport } from "../../src/package/report.js";
import type { GltfpackInfo } from "../../src/package/tool.js";
import { packageResults, wantsPackage } from "../../src/package/rules.js";

const VALIDATION = { validator: "2.0.0", seconds: 0, bytes: 0, errors: 0, warnings: 0, infos: 0, hints: 0, issues: [], refused: [] };
const GPU = { textureBytes: 0, meshBytes: 0, totalBytes: 0, images: [] };
const EQUIVALENT = { pass: true, tolerance: 0.001, checks: [{ name: "bounds", pass: true, detail: "" }] };

function file(overrides: Partial<PackageFile["compressed"]> = {}): PackageFile {
  const packed = { path: "x.glb", bytes: 1000, sha256: "a", validation: VALIDATION, gpu: GPU, extensionsUsed: ["EXT_meshopt_compression"] };
  return { level: null, uncompressed: { ...packed, bytes: 5000, extensionsUsed: [] }, compressed: { ...packed, equivalence: EQUIVALENT, ...overrides } };
}

function level(index: number, ratio: number, extra: Record<string, unknown> = {}) {
  const view = { view: "front", lod0: "a", lod: "b", silhouetteIou: 0.99, similarity: 0.95, silhouettePixels: [10, 10] as [number, number] };
  return {
    level: index,
    names: [],
    triangles: Math.round(ratio * 1000),
    ratio,
    bounds: { min: [0, 0, 0] as [number, number, number], max: [1, 1, 1] as [number, number, number] },
    screenErrorPixels: 0.8,
    uvOverlap: 0,
    render: { level: index, distance: 5, crop: 256, views: [view], silhouetteIou: 0.99, similarity: 0.95, similarityMean: 0.95 },
    ...extra,
  };
}

const GLTFPACK: GltfpackInfo = { kind: "npm", version: "1.3.0", source: "npm package", sha256: null, ktx2: false, ktx2Reason: "no encoder", meshopt: true, nativeSkipped: null, isolation: null };

function report(overrides: Partial<PackageReport> = {}): PackageReport {
  return {
    stem: "x",
    layout: "single",
    requested: { lods: null, package: null },
    levels: [{ ...level(0, 1), render: null }, level(1, 0.5), level(2, 0.25)],
    roundTrip: [{ name: "blenderImport", pass: true, detail: "" }],
    render: { status: "rendered", reason: null, device: null, views: ["front"], samples: 16, sheet: null, sheetSha256: null, budget: { samplePixels: 0, maxSamplePixels: 1 } },
    compression: { meshopt: true, ktx2: { requested: false, status: "not requested", reason: null }, arguments: [], gltfpack: GLTFPACK },
    files: [file()],
    sizes: { uncompressedBytes: 5000, compressedBytes: 1000, ratio: 0.2, gpu: { before: { files: 0, textureBytes: 0, meshBytes: 0, totalBytes: 0 }, after: { files: 0, textureBytes: 0, meshBytes: 0, totalBytes: 0 } } },
    seconds: 1,
    ...overrides,
  };
}

function verdicts(spec: Record<string, unknown>, value: PackageReport): Record<string, boolean> {
  return Object.fromEntries(packageResults(parseSpec({ format: "glb", ...spec }), value).map((rule) => [rule.rule, rule.pass]));
}

const LODS = { count: 2, ratios: [0.5, 0.25], minSilhouetteIoU: 0.95, minSimilarity: 0.9 };

describe("the lods and package spec groups", () => {
  it("accepts ratios or a screen error with distances, and the package options", () => {
    expect(parseSpec({ format: "glb", lods: LODS, package: { compressedMaxBytes: 1000, ktx2: false, meshopt: true } }).lods?.count).toBe(2);
    expect(parseSpec({ format: "glb", lods: { count: 2, maxScreenError: 1.5, distances: [5, 10], files: "separate" } }).lods?.files).toBe("separate");
    expect(parseSpec({ format: "glb", package: {} }).package).toEqual({});
    expect(wantsPackage(parseSpec({ format: "glb" }))).toBe(false);
    expect(wantsPackage(parseSpec({ format: "glb", package: {} }))).toBe(true);
  });

  it("refuses ratios that do not fall, count mismatches, both or neither mode, and a screen error without distances", () => {
    const bad = (lods: Record<string, unknown>) => () => parseSpec({ format: "glb", lods });
    expect(bad({ count: 2, ratios: [0.25, 0.5] })).toThrow(SpecError);
    expect(bad({ count: 2, ratios: [0.5] })).toThrow("one value per level");
    expect(bad({ count: 1 })).toThrow("exactly one of ratios and maxScreenError");
    expect(bad({ count: 1, ratios: [0.5], maxScreenError: 1, distances: [5] })).toThrow("exactly one");
    expect(bad({ count: 1, maxScreenError: 1 })).toThrow("needs distances");
    expect(bad({ count: 2, maxScreenError: 1, distances: [10, 5] })).toThrow("each larger");
    expect(bad({ count: 9, ratios: Array(9).fill(0.5) })).toThrow(SpecError);
    expect(bad({ count: 1, ratios: [1] })).toThrow(SpecError);
    expect(bad({ count: 1, ratios: [0.5], extra: true })).toThrow(SpecError);
    expect(() => parseSpec({ format: "glb", package: { ktx2: "yes" } })).toThrow(SpecError);
  });
});

describe("package rules", () => {
  it("pass for a report that meets every limit", () => {
    expect(verdicts({ lods: LODS, package: { compressedMaxBytes: 2000, meshopt: true } }, report())).toEqual({
      "lods.count": true,
      "lods.ratios": true,
      "lods.minSilhouetteIoU": true,
      "lods.minSimilarity": true,
      "package.validator": true,
      "package.equivalent": true,
      "package.compressedMaxBytes": true,
      "package.meshopt": true,
    });
  });

  it("fail the silhouette rule for a LOD below the threshold, and when no silhouette was measured", () => {
    const broken = report({ levels: [{ ...level(0, 1), render: null }, level(1, 0.5), level(2, 0.25, { render: { ...level(2, 0.25).render, silhouetteIou: 0.6 } })] });
    expect(verdicts({ lods: LODS }, broken)["lods.minSilhouetteIoU"]).toBe(false);
    const skipped = report({ levels: [{ ...level(0, 1), render: null }, level(1, 0.5, { render: null }), level(2, 0.25, { render: null })] });
    const results = packageResults(parseSpec({ format: "glb", lods: LODS }), skipped);
    const rule = results.find((entry) => entry.rule === "lods.minSilhouetteIoU");
    expect(rule).toMatchObject({ measured: null, pass: false });
    expect(verdicts({ lods: LODS }, skipped)["lods.minSimilarity"]).toBe(false);
  });

  it("fail the ratio rule when locks keep a LOD above its target, and pass within the reach tolerance", () => {
    expect(verdicts({ lods: LODS }, report({ levels: [{ ...level(0, 1), render: null }, level(1, 0.5), level(2, 0.4)] }))["lods.ratios"]).toBe(false);
    expect(verdicts({ lods: LODS }, report({ levels: [{ ...level(0, 1), render: null }, level(1, 0.52), level(2, 0.26)] }))["lods.ratios"]).toBe(true);
    expect(verdicts({ lods: LODS }, report({ levels: [{ ...level(0, 1), render: null }, level(1, 0.5)] }))["lods.count"]).toBe(false);
  });

  it("check the screen error of every level against the limit", () => {
    const spec = { lods: { count: 2, maxScreenError: 1, distances: [5, 10] } };
    expect(verdicts(spec, report())["lods.maxScreenError"]).toBe(true);
    const over = report({ levels: [{ ...level(0, 1), render: null }, level(1, 0.5), level(2, 0.25, { screenErrorPixels: 1.4 })] });
    expect(verdicts(spec, over)["lods.maxScreenError"]).toBe(false);
  });

  it("fail when the validator reports errors in either package, or the package holds no file", () => {
    const bad = { ...VALIDATION, errors: 1 };
    expect(verdicts({ package: {} }, report({ files: [file({ validation: bad })] }))["package.validator"]).toBe(false);
    const uncompressed = file();
    uncompressed.uncompressed.validation = bad;
    expect(verdicts({ package: {} }, report({ files: [uncompressed] }))["package.validator"]).toBe(false);
    expect(verdicts({ package: {} }, report({ files: [] }))["package.validator"]).toBe(false);
  });

  it("fail when an equivalence check or the Blender import check fails, or the import was not run", () => {
    const failed = file({ equivalence: { pass: false, tolerance: 0.001, checks: [{ name: "bounds", pass: false, detail: "moved" }] } });
    expect(verdicts({ package: {} }, report({ files: [failed] }))["package.equivalent"]).toBe(false);
    expect(verdicts({ package: {} }, report({ roundTrip: [{ name: "blenderImport", pass: false, detail: "" }] }))["package.equivalent"]).toBe(false);
    expect(verdicts({ package: {} }, report({ roundTrip: null }))["package.equivalent"]).toBe(false);
  });

  it("fail the size, KTX2 and meshopt rules honestly", () => {
    expect(verdicts({ package: { compressedMaxBytes: 500 } }, report())["package.compressedMaxBytes"]).toBe(false);
    const unavailable = report({ compression: { meshopt: true, ktx2: { requested: true, status: "unavailable", reason: "no encoder" }, arguments: [], gltfpack: GLTFPACK } });
    expect(verdicts({ package: { ktx2: true } }, unavailable)["package.ktx2"]).toBe(false);
    const written = report({ compression: { meshopt: true, ktx2: { requested: true, status: "written", reason: null }, arguments: [], gltfpack: GLTFPACK } });
    expect(verdicts({ package: { ktx2: true } }, written)["package.ktx2"]).toBe(true);
    expect(verdicts({ package: { ktx2: false } }, unavailable)).not.toHaveProperty("package.ktx2");
    expect(verdicts({ package: { meshopt: false } }, report())["package.meshopt"]).toBe(false);
    expect(verdicts({ package: { meshopt: false } }, report({ files: [file({ extensionsUsed: [] })] }))["package.meshopt"]).toBe(true);
    expect(verdicts({ package: { meshopt: true } }, report({ files: [file({ extensionsUsed: [] })] }))["package.meshopt"]).toBe(false);
  });
});
