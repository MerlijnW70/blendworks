import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { judge } from "../../src/judge/run.js";
import { analyse } from "../../src/package/analysis.js";
import { packageAsset, parsePackage, type PackageCommand } from "../../src/package/cli.js";
import { compress } from "../../src/package/compress.js";
import { buildGlb, parseGlb } from "../../src/package/glb.js";
import { imageBytes } from "../../src/package/memory.js";
import { selectNative } from "../../src/package/native.js";
import { freshDir, makeFixtureSet } from "../judge/helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const NATIVE_KTX2 = (await selectNative()).tool?.ktx2.ktx2 === true;

let assets = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtureSet("package_fixtures", "package"));
}));

function command(argv: string[]): Omit<PackageCommand, "command"> {
  const parsed = parsePackage(argv);
  if ("help" in parsed) throw new Error("help requested");
  const { command: _, ...rest } = parsed;
  return rest;
}

function glbOf(path: string) {
  return parseGlb(new Uint8Array(readFileSync(path)));
}

describe("packaging a textured asset through the judge", workBudget(300_000), () => {
  it("builds LODs, renders them against LOD0 and compresses with gltfpack, writing KTX2 with the native build and saying plainly that it cannot without", async () => {
    const dir = freshDir("package", "judge-ball");
    const specPath = join(dir, "ball.spec.json");
    writeFileSync(
      specPath,
      JSON.stringify({
        name: "painted ball",
        format: "glb",
        views: ["front", "three-quarter"],
        lods: { count: 2, ratios: [0.5, 0.25], minSilhouetteIoU: 0.9, minSimilarity: 0.7 },
        package: { compressedMaxBytes: 400_000, meshopt: true, ktx2: true },
      }),
    );
    const outDir = join(dir, "out");
    const report = await judge({ specPath, assetPath: join(assets, "textured-ball.glb"), outDir });
    const rules = Object.fromEntries(report.rules.map((rule) => [rule.rule, rule]));
    expect(report.failure).toBeNull();
    expect(Object.keys(rules).filter((name) => /^(lods|package)\./.test(name))).toEqual([
      "lods.count",
      "lods.ratios",
      "lods.minSilhouetteIoU",
      "lods.minSimilarity",
      "package.validator",
      "package.equivalent",
      "package.compressedMaxBytes",
      "package.ktx2",
      "package.meshopt",
    ]);
    for (const name of Object.keys(rules).filter((rule) => rule !== "package.ktx2")) expect(rules[name], name).toMatchObject({ pass: true });
    if (NATIVE_KTX2) {
      expect(rules["package.ktx2"]).toMatchObject({ pass: true, measured: "written" });
      expect(report.passed).toBe(true);
    } else {
      expect(rules["package.ktx2"]).toMatchObject({ pass: false });
      expect(String(rules["package.ktx2"]?.measured)).toContain("unavailable: gltfpack was built without BasisU support");
      expect(report.passed).toBe(false);
    }
    const packaged = report.package!;
    expect(packaged.levels.map((level) => level.triangles)).toEqual([3968, expect.any(Number), expect.any(Number)]);
    expect(Math.abs(packaged.levels[1]!.triangles - 1984)).toBeLessThanOrEqual(120);
    expect(Math.abs(packaged.levels[2]!.triangles - 992)).toBeLessThanOrEqual(60);
    for (const level of packaged.levels.slice(1)) {
      expect(level.error?.hausdorff).toBeGreaterThan(0);
      expect(level.error?.hausdorffFraction).toBeCloseTo((level.error?.hausdorff ?? 0) / level.error!.diagonal, 9);
      expect(level.render?.views.map((view) => view.view)).toEqual(["front", "three-quarter"]);
      expect(level.render?.silhouetteIou).toBeGreaterThan(0.9);
    }
    expect(packaged.render.status).toBe("rendered");
    expect(existsSync(packaged.render.sheet!)).toBe(true);
    expect(packaged.roundTrip?.every((check) => check.pass)).toBe(true);
    const [file] = packaged.files;
    expect(file?.uncompressed.validation.errors).toBe(0);
    expect(file?.compressed.validation.errors).toBe(0);
    expect(file?.compressed.equivalence.pass).toBe(true);
    expect(file?.compressed.bytes).toBeLessThan(file!.uncompressed.bytes);
    expect(file?.compressed.extensionsUsed).toContain("EXT_meshopt_compression");
    expect(file?.uncompressed.extensionsUsed).not.toContain("EXT_meshopt_compression");
    expect(packaged.compression.ktx2).toMatchObject({ requested: true, status: NATIVE_KTX2 ? "written" : "unavailable" });
    expect(packaged.compression.gltfpack.kind).toBe(NATIVE_KTX2 ? "native" : "npm");
    const sizes = packaged.sizes.gpu;
    expect(sizes.before.textureBytes).toBe(imageBytes(128, 128, "rgba8") + 2 * imageBytes(64, 64, "rgba8"));
    if (NATIVE_KTX2) expect(sizes.after.textureBytes).toBeLessThan(sizes.before.textureBytes);
    else expect(sizes.after.textureBytes).toBe(sizes.before.textureBytes);
    expect(sizes.after.meshBytes).toBeLessThan(sizes.before.meshBytes);
    const source = analyse(glbOf(join(outDir, "package", file!.uncompressed.path)).json);
    const packed = analyse(glbOf(join(outDir, "package", file!.compressed.path)).json);
    expect(packed.images.map((image) => image.mimeType)).toEqual(source.images.map((image) => (NATIVE_KTX2 ? "image/ktx2" : image.mimeType)));
    expect(source.paths).toEqual(["/Ball_LOD0", "/Ball_LOD1", "/Ball_LOD2"]);
    expect(packed.paths).toEqual(source.paths);
    expect(JSON.parse(readFileSync(join(outDir, "report.json"), "utf8")).package.files[0].compressed.sha256).toBe(file?.compressed.sha256);
    expect(report.summary).toContain("LOD sheet:");
  });

  it("fails minSilhouetteIoU for a LOD whose silhouette is deliberately broken", async () => {
    const dir = freshDir("package", "judge-ring");
    const specPath = join(dir, "ring.spec.json");
    writeFileSync(specPath, JSON.stringify({ format: "glb", views: ["front", "three-quarter"], lods: { count: 1, ratios: [0.03], distances: [1.2], minSilhouetteIoU: 0.9 } }));
    const report = await judge({ specPath, assetPath: join(assets, "thin-ring.glb"), outDir: join(dir, "out"), preview: false });
    const rule = report.rules.find((entry) => entry.rule === "lods.minSilhouetteIoU");
    expect(rule?.pass).toBe(false);
    expect(Number(rule?.measured)).toBeLessThan(0.8);
    expect(report.rules.find((entry) => entry.rule === "lods.ratios")?.pass).toBe(true);
    expect(report.passed).toBe(false);
  });

  it("measures no silhouette in a preview, so a silhouette rule cannot pass without the renders", async () => {
    const dir = freshDir("package", "judge-preview");
    const specPath = join(dir, "ball.spec.json");
    writeFileSync(specPath, JSON.stringify({ format: "glb", lods: { count: 1, ratios: [0.5], minSilhouetteIoU: 0.5 } }));
    const report = await judge({ specPath, assetPath: join(assets, "textured-ball.glb"), outDir: join(dir, "out"), preview: true });
    expect(report.package?.render).toMatchObject({ status: "skipped", reason: "preview" });
    expect(report.rules.find((entry) => entry.rule === "lods.minSilhouetteIoU")).toMatchObject({ measured: null, pass: false });
    expect(report.package?.roundTrip?.every((check) => check.pass)).toBe(true);
  });

  it("keeps a spec without lods and package exactly as before", async () => {
    const dir = freshDir("package", "judge-plain");
    const specPath = join(dir, "plain.spec.json");
    writeFileSync(specPath, JSON.stringify({ format: "glb", triangles: { max: 5000 } }));
    const outDir = join(dir, "out");
    const report = await judge({ specPath, assetPath: join(assets, "textured-ball.glb"), outDir, preview: true });
    expect(report.package).toBeUndefined();
    expect(Object.keys(JSON.parse(readFileSync(join(outDir, "report.json"), "utf8")))).not.toContain("package");
    expect(existsSync(join(outDir, "package"))).toBe(false);
    expect(report.passed).toBe(true);
  });

  it("packages without LODs when only the package rule is given", async () => {
    const dir = freshDir("package", "judge-compress-only");
    const specPath = join(dir, "ball.spec.json");
    writeFileSync(specPath, JSON.stringify({ format: "glb", package: { meshopt: true } }));
    const report = await judge({ specPath, assetPath: join(assets, "textured-ball.glb"), outDir: join(dir, "out"), preview: true });
    expect(report.package?.levels.map((level) => level.level)).toEqual([0]);
    expect(report.package?.files[0]?.compressed.equivalence.pass).toBe(true);
    expect(report.passed).toBe(true);
  });
});

describe("the package command", workBudget(300_000), () => {
  it("writes one file per LOD when asked and keeps the parent empties and names in both packages", async () => {
    const outDir = freshDir("package", "cli-rig");
    const run = await packageAsset(command([join(assets, "rig.glb"), "--out", outDir, "--lods", "1", "--ratios", "0.5", "--files", "separate", "--views", "front"]));
    expect(run.passed).toBe(true);
    expect(run.report.files.map((file) => file.compressed.path)).toEqual(["compressed/rig_LOD0.glb", "compressed/rig_LOD1.glb"]);
    const paths = run.report.files.map((file) => analyse(glbOf(join(outDir, file.compressed.path)).json).paths);
    expect(paths[0]).toEqual(["/Rig", "/Rig/Arm_LOD0", "/Rig/Hand_LOD0"]);
    expect(paths[1]).toEqual(["/Rig", "/Rig/Arm_LOD1", "/Rig/Hand_LOD1"]);
    expect(run.report.files.every((file) => file.compressed.equivalence.pass)).toBe(true);
    expect(run.report.levels[1]?.render?.views).toHaveLength(1);
    expect(existsSync(join(outDir, "package-report.json"))).toBe(true);
    expect(run.summary).toMatch(/^PASS {2}package/);
  });

  it("works from a screen-space error at stated distances", async () => {
    const outDir = freshDir("package", "cli-screen");
    const run = await packageAsset(command([join(assets, "textured-ball.glb"), "--out", outDir, "--lods", "2", "--max-screen-error", "2", "--distances", "4,12", "--views", "front"]));
    expect(run.passed).toBe(true);
    const [, first, second] = run.report.levels;
    expect(first?.distance).toBe(4);
    expect(second?.distance).toBe(12);
    expect(first!.screenErrorPixels!).toBeLessThanOrEqual(2.0002);
    expect(second!.screenErrorPixels!).toBeLessThanOrEqual(2.0002);
    expect(second!.triangles).toBeLessThan(first!.triangles);
  });

  it("fails when validation of a corrupted compressed output reports errors", async () => {
    const outDir = freshDir("package", "cli-corrupt");
    const corrupting: typeof compress = async (input, options) => {
      const result = await compress(input, options);
      const { json, bin } = parseGlb(result.output);
      ((json.meshes as { primitives: { mode?: number }[] }[])[0]!.primitives[0] as { mode?: number }).mode = 99;
      return { ...result, output: buildGlb(json, bin) };
    };
    const run = await packageAsset(command([join(assets, "textured-ball.glb"), "--out", outDir]), { compressor: corrupting });
    expect(run.report.files[0]?.compressed.validation.errors).toBeGreaterThan(0);
    expect(run.summary).toMatch(/FAIL {2}package\.validator/);
    expect(run.passed).toBe(false);
  });

  it("fails when the compressed package moves its geometry beyond the quantisation tolerance", async () => {
    const outDir = freshDir("package", "cli-shifted");
    const shifting: typeof compress = async (input, options) => {
      const result = await compress(input, options);
      const { json, bin } = parseGlb(result.output);
      const holder = (json.nodes as { name?: string; translation?: number[]; mesh?: number }[]).find((node) => node.name === undefined && node.mesh !== undefined)!;
      holder.translation = [(holder.translation?.[0] ?? 0) + 0.05, holder.translation?.[1] ?? 0, holder.translation?.[2] ?? 0];
      return { ...result, output: buildGlb(json, bin) };
    };
    const run = await packageAsset(command([join(assets, "textured-ball.glb"), "--out", outDir]), { compressor: shifting });
    const checks = run.report.files[0]!.compressed.equivalence.checks;
    expect(checks.find((check) => check.name === "bounds")?.pass).toBe(false);
    expect(checks.find((check) => check.name === "bounds")?.detail).toContain("differs by 0.05");
    expect(checks.find((check) => check.name === "triangles")?.pass).toBe(true);
    expect(checks.find((check) => check.name === "hierarchy")?.pass).toBe(true);
    expect(run.summary).toMatch(/FAIL {2}package\.equivalent/);
    expect(run.passed).toBe(false);
  });
});

describe("the package command line", () => {
  it("turns flags into the same rules a spec gives", () => {
    const parsed = command(["x.glb", "--out", "o", "--lods", "2", "--ratios", "0.5,0.2", "--min-iou", "0.9", "--min-similarity", "0.8", "--ktx2", "--no-meshopt", "--max-bytes", "1000", "--views", "front,top"]);
    expect(parsed.config).toEqual({
      lods: { count: 2, ratios: [0.5, 0.2], minSilhouetteIoU: 0.9, minSimilarity: 0.8 },
      package: { ktx2: true, meshopt: false, compressedMaxBytes: 1000 },
      views: ["front", "top"],
    });
  });

  it("refuses what a spec would refuse, and a missing out folder", () => {
    expect(() => parsePackage(["x.glb", "--out", "o", "--lods", "2", "--ratios", "0.5"])).toThrow("one value per level");
    expect(() => parsePackage(["x.glb", "--out", "o", "--lods", "2"])).toThrow("exactly one of ratios and maxScreenError");
    expect(() => parsePackage(["x.glb", "--lods", "1", "--ratios", "0.5"])).toThrow("usage: blendworks package");
    expect(() => parsePackage(["x.glb", "--out", "o", "--lods", "1", "--ratios", "a"])).toThrow("comma-separated list of numbers");
  });
});
