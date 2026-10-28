import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import type { Report } from "../../src/judge/report.js";
import { judge, type JudgeOptions } from "../../src/judge/run.js";
import { freshDir, makeTextureFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(withWorkBudget(180_000, () => {
  assets = makeTextureFixtures("textures");
  specs = freshDir("textures", "specs");
}));

const BASE = 4 * (64 * 64 + 32 * 32 + 16 * 16 + 8 * 8 + 4 * 4 + 2 * 2 + 1 * 1);
const BASE_TRIM = 4 * (32 * 32 + 16 * 16 + 8 * 8 + 4 * 4 + 2 * 2 + 1 * 1);
const ORM = BASE_TRIM;
const NORMAL = BASE;
const EMIT = 4 * (16 * 16 + 8 * 8 + 4 * 4 + 2 * 2 + 1 * 1);
const NPOT_BASE = 4 * (48 * 20 + 24 * 10 + 12 * 5 + 6 * 2 + 3 * 1 + 1 * 1);
const EVERY_KIND = ["baseColor", "metallicRoughness", "normal", "emissive", "occlusion"];

const TEXTURE_SPEC = {
  name: "textured box",
  format: "glb",
  textures: { required: EVERY_KIND, minSize: 16, maxSize: 64, embedded: true, maxCount: 5, maxGpuBytes: 55_972, powerOfTwo: true },
  views: ["three-quarter"],
};

const TEXTURE_RULES = [
  "format",
  "textures.required",
  "textures.minSize",
  "textures.maxSize",
  "textures.embedded",
  "textures.maxCount",
  "textures.maxGpuBytes",
  "textures.powerOfTwo",
];

async function judged(asset: string, overrides: Record<string, unknown> = {}, options: Partial<JudgeOptions> = { preview: true }): Promise<Report> {
  const name = asset.replace(/\W+/g, "-");
  const spec = join(specs, `${name}.spec.json`);
  writeFileSync(spec, JSON.stringify({ ...TEXTURE_SPEC, ...overrides }, null, 2));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("textures", "reports", name), ...options });
}

function failing(report: Report): string[] {
  return report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule);
}

function rule(report: Report, name: string) {
  return report.rules.find((entry) => entry.rule === name);
}

function image(name: string, kinds: string[], materials: string[], width: number, height: number, gpuBytes: number, colourSpace: string) {
  const powerOfTwo = [width, height].every((side) => (side & (side - 1)) === 0);
  return { name, kinds, materials, width, height, colourSpace, embedded: true, source: "packed", file: null, gpuBytes, powerOfTwo };
}

const TEXTURED_IMAGES = [
  image("base", ["baseColor"], ["painted"], 64, 64, BASE, "sRGB"),
  image("base_trim", ["baseColor"], ["trim"], 32, 32, BASE_TRIM, "sRGB"),
  image("emit", ["emissive"], ["painted", "trim"], 16, 16, EMIT, "sRGB"),
  image("normal", ["normal"], ["painted", "trim"], 64, 64, NORMAL, "Non-Color"),
  image("orm", ["metallicRoughness", "occlusion"], ["painted", "trim"], 32, 32, ORM, "Non-Color"),
];

describe("texture rules on generated PBR assets", workBudget(120_000), () => {
  it("passes every texture rule for the box with five embedded maps, in preview mode", async () => {
    const report = await judged("textured.glb");
    expect(report.rules.map((entry) => entry.rule)).toEqual(TEXTURE_RULES);
    expect(failing(report)).toEqual([]);
    expect(report.passed).toBe(true);
    expect(report.renders?.viewsSkipped).toBe(true);
    const textures = report.measurements!.textures!;
    expect(textures.images).toEqual(TEXTURED_IMAGES);
    expect(textures.materials).toEqual([
      { name: "painted", maps: EVERY_KIND },
      { name: "trim", maps: EVERY_KIND },
    ]);
    expect(textures.count).toBe(5);
    expect([textures.smallestSide, textures.largestSide]).toEqual([16, 64]);
    expect(textures.colourSpaceMismatches).toEqual({ count: 0, items: [] });
    expect(rule(report, "textures.required")).toEqual({ rule: "textures.required", measured: { materials: 2, missing: [] }, limit: EVERY_KIND, pass: true });
    expect(report.summary).toContain("pass  textures.minSize      measured 16; required at least 16");
    expect(report.summary).toContain("pass  textures.maxGpuBytes  measured 55972; required at most 55972");
    expect(report.summary).toContain("  textures: 5 images, GPU estimate 55972 bytes (0.1 MiB, RGBA8 with mips)");
    expect(report.summary).toContain("  colour spaces: right for every map");
  });

  it("estimates GPU memory as RGBA8 with a full mip chain, worked out per image", async () => {
    expect(BASE + BASE_TRIM + ORM + NORMAL + EMIT).toBe(55_972);
    expect(NPOT_BASE).toBe(5104);
    const textured = await judged("textured.glb", { textures: { maxGpuBytes: 55_971 } });
    expect(rule(textured, "textures.maxGpuBytes")).toEqual({ rule: "textures.maxGpuBytes", measured: 55_972, limit: 55_971, pass: false });
    const npot = await judged("npot.glb", { textures: { maxGpuBytes: 100_000 } });
    expect(npot.measurements?.textures?.images.find((entry) => entry.name === "base")).toMatchObject({ width: 48, height: 20, gpuBytes: NPOT_BASE });
    expect(npot.measurements?.textures?.gpuBytes).toBe(NPOT_BASE + BASE_TRIM + ORM + NORMAL + EMIT);
  });

  it("fails textures.required when the normal map is missing", async () => {
    const report = await judged("missing-normal.glb");
    expect(failing(report)).toEqual(["textures.required"]);
    expect(rule(report, "textures.required")?.measured).toEqual({ materials: 2, missing: ["normal: painted, trim"] });
    expect(report.measurements?.textures?.materials).toEqual([
      { name: "painted", maps: ["baseColor", "metallicRoughness", "emissive", "occlusion"] },
      { name: "trim", maps: ["baseColor", "metallicRoughness", "emissive", "occlusion"] },
    ]);
    expect(report.measurements?.textures?.gpuBytes).toBe(BASE + BASE_TRIM + ORM + EMIT);
    expect(report.summary).toContain("FAIL  textures.required     measured materials 2, missing [\"normal: painted, trim\"]; required [baseColor, metallicRoughness, normal, emissive, occlusion]");
  });

  it("reports a data map in the sRGB colour space as a mismatch of its own", async () => {
    const report = await judged("wrong-colour.blend", { format: "blend" });
    expect(failing(report)).toEqual([]);
    const textures = report.measurements!.textures!;
    expect(textures.colourSpaceMismatches).toEqual({ count: 1, items: [{ image: "normal", kind: "normal", colourSpace: "sRGB", expected: "Non-Color" }] });
    expect(textures.images.find((entry) => entry.name === "normal")).toMatchObject({ colourSpace: "sRGB", embedded: true, source: "generated" });
    expect(report.summary).toContain('  colour spaces: 1 wrong\n    "normal" as normal is sRGB, expected Non-Color');
  });

  it("fails textures.embedded for a .gltf whose images are files beside it, and still renders them", async () => {
    const report = await judged("external/external.gltf", { format: "gltf" }, { device: "cpu" });
    expect(failing(report)).toEqual(["textures.embedded"]);
    const external = ["base (base.png)", "base_trim (base_trim.png)", "emit (emit.png)", "normal (normal.png)", "orm (orm.png)"];
    expect(rule(report, "textures.embedded")).toEqual({ rule: "textures.embedded", measured: { external: 5, images: external }, limit: { external: 0 }, pass: false });
    expect(report.measurements?.textures?.images.map((entry) => [entry.name, entry.embedded, entry.source, entry.file])).toEqual([
      ["base", false, "file", "base.png"],
      ["base_trim", false, "file", "base_trim.png"],
      ["emit", false, "file", "emit.png"],
      ["normal", false, "file", "normal.png"],
      ["orm", false, "file", "orm.png"],
    ]);
    expect(report.measurements?.textures?.gpuBytes).toBe(55_972);
    expect(report.failure).toBeNull();
    expect(report.renders?.views).toHaveLength(1);
  });

  it("counts images in data URIs as embedded, and the validator decodes them without opening anything", async () => {
    const folder = join(assets, "external");
    const document = JSON.parse(readFileSync(join(folder, "external.gltf"), "utf8"));
    const inline = (mime: string, file: string) => `data:${mime};base64,${readFileSync(join(folder, file)).toString("base64")}`;
    for (const entry of document.images) entry.uri = inline("image/png", entry.uri);
    document.buffers[0].uri = inline("application/octet-stream", document.buffers[0].uri);
    mkdirSync(join(assets, "inline"), { recursive: true });
    writeFileSync(join(assets, "inline", "inline.gltf"), JSON.stringify(document));
    const report = await judged("inline/inline.gltf", { format: "gltf", gltf: { validator: { maxWarnings: 0 } } });
    expect(failing(report)).toEqual([]);
    expect(report.measurements?.textures?.images.map((entry) => [entry.name, entry.source])).toEqual(TEXTURED_IMAGES.map((entry) => [entry.name, "packed"]));
    expect(report.validation).toMatchObject({ errors: 0, warnings: 0, refused: [] });
  });

  it("fails textures.powerOfTwo for the 48 x 20 base colour map", async () => {
    const report = await judged("npot.glb");
    expect(failing(report)).toEqual(["textures.powerOfTwo"]);
    expect(rule(report, "textures.powerOfTwo")).toEqual({ rule: "textures.powerOfTwo", measured: { nonPowerOfTwo: 1, images: ["base 48x20"] }, limit: { nonPowerOfTwo: 0 }, pass: false });
    const relaxed = await judged("npot.glb", { textures: { ...TEXTURE_SPEC.textures, powerOfTwo: false } });
    expect(failing(relaxed)).toEqual([]);
    expect(relaxed.rules.map((entry) => entry.rule)).not.toContain("textures.powerOfTwo");
  });

  it("fails the size limits on the shorter and the longer side", async () => {
    const report = await judged("npot.glb", { textures: { minSize: 32, maxSize: 32 } });
    expect(failing(report)).toEqual(["textures.minSize", "textures.maxSize"]);
    expect(rule(report, "textures.minSize")?.measured).toBe(16);
    expect(rule(report, "textures.maxSize")?.measured).toBe(64);
  });

  it("names the texture count and GPU estimate on the contact sheet header", async () => {
    const script = [
      "import sys",
      `sys.path.insert(0, ${JSON.stringify(resolve("bridge", "judge"))})`,
      "from judge_sheet import texture_line",
      "print('LINE', texture_line({'count': 3, 'gpuBytes': 268435452}))",
      "print('LINE', texture_line({'count': 1, 'gpuBytes': 5104}))",
      "print('LINE', texture_line(None))",
    ].join("\n");
    const output = execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-expr", script], { encoding: "utf8", timeout: 60_000 });
    expect(output.split(/\r?\n/).filter((line) => line.startsWith("LINE "))).toEqual([
      "LINE 3 TEXTURES   GPU ESTIMATE 256.0 MIB (RGBA8 WITH MIPS)",
      "LINE 1 TEXTURE   GPU ESTIMATE 0.0 MIB (RGBA8 WITH MIPS)",
      "LINE TEXTURES NOT MEASURED",
    ]);
    const report = await judged("textured.glb", { name: "header" });
    const measured = JSON.parse(readFileSync(join(report.renders!.contactSheet!, "..", "measurements.json"), "utf8"));
    expect(measured.measurements.textures).toMatchObject({ count: 5, gpuBytes: 55_972 });
  });
});
