import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge, type JudgeOptions } from "../../src/judge/run.js";
import { REFUSAL_REASONS } from "../../src/judge/path-policy.js";
import { resolveResource, validateGltf, ValidationError, VALIDATOR_DEFAULTS } from "../../src/judge/validator.js";
import { freshDir, makeTextureFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let work = "";

beforeAll(withWorkBudget(180_000, () => {
  assets = makeTextureFixtures("validator");
  work = freshDir("validator", "work");
}));

const LIMITS = { maxBytes: VALIDATOR_DEFAULTS.maxBytes, heapMb: VALIDATOR_DEFAULTS.heapMb, timeoutMs: 60_000 };
const PLAIN_SPEC = { name: "plain cube", format: "glb", gltf: { validator: {} }, views: ["front"] };

async function judged(asset: string, spec: Record<string, unknown>, options: Partial<JudgeOptions> = {}): Promise<{ report: Report; outDir: string }> {
  const name = `${asset.replace(/\W+/g, "-")}-${Object.keys(spec).join("-")}`;
  const specPath = join(work, `${name}.spec.json`);
  writeFileSync(specPath, JSON.stringify(spec));
  const outDir = freshDir("validator", "reports", name);
  const report = await judge({ specPath, assetPath: join(assets, asset), outDir, preview: true, ...options });
  return { report, outDir };
}

function failing(report: Report): string[] {
  return report.rules.filter((rule) => !rule.pass).map((rule) => rule.rule);
}

function gltfWithImage(name: string, uri: string): string {
  const document = JSON.parse(readFileSync(join(assets, "external", "external.gltf"), "utf8"));
  document.images[0].uri = uri;
  const path = join(assets, "external", name);
  writeFileSync(path, JSON.stringify(document));
  return path;
}

describe("the Khronos glTF validator", workBudget(120_000), () => {
  it("reports 0 errors and 0 warnings for clean exports", async () => {
    for (const [asset, format] of [["plain.glb", "glb"], ["textured.glb", "glb"], ["external/external.gltf", "gltf"]] as const) {
      const validation = await validateGltf(join(assets, asset), format, LIMITS);
      expect([validation.errors, validation.warnings], asset).toEqual([0, 0]);
      expect(validation.validator).toBe("2.0.0-dev.3.10");
      expect(validation.refused).toEqual([]);
    }
  });

  it("lists every issue with its code, severity, pointer and message for a broken accessor", async () => {
    const validation = await validateGltf(join(assets, "wrong-bounds.glb"), "glb", LIMITS);
    expect(validation.errors).toBe(3);
    const errors = validation.issues.filter((issue) => issue.severity === "error");
    expect(errors.map((issue) => [issue.code, issue.pointer])).toEqual([
      ["ACCESSOR_MAX_MISMATCH", "/accessors/0/max/0"],
      ["ACCESSOR_MAX_MISMATCH", "/accessors/0/max/1"],
      ["ACCESSOR_MAX_MISMATCH", "/accessors/0/max/2"],
    ]);
    expect(errors[0]?.message).toBe("Declared maximum value for this component (2) does not match actual maximum (0.5).");
    expect(validation.issues).toHaveLength(validation.errors + validation.warnings + validation.infos + validation.hints);
  });

  it("fails gltf.validator on the broken accessor in the judge, while every other measurement still passes", async () => {
    const { report, outDir } = await judged("wrong-bounds.glb", PLAIN_SPEC);
    expect(report.failure).toBeNull();
    expect(failing(report)).toEqual(["gltf.validator.maxErrors"]);
    expect(report.rules.find((rule) => rule.rule === "gltf.validator.maxErrors")).toEqual({ rule: "gltf.validator.maxErrors", measured: 3, limit: 0, pass: false });
    expect(report.validation?.issues.filter((issue) => issue.code === "ACCESSOR_MAX_MISMATCH")).toHaveLength(3);
    expect(report.summary).toContain("FAIL  gltf.validator.maxErrors  measured 3; required at most 0");
    expect(report.summary).toContain("    error ACCESSOR_MAX_MISMATCH at /accessors/0/max/0: Declared maximum value");
    expect(JSON.parse(readFileSync(join(outDir, "validation.json"), "utf8"))).toMatchObject({ ok: true, errors: 3 });
    const clean = await judged("plain.glb", { ...PLAIN_SPEC, gltf: { validator: { maxErrors: 0, maxWarnings: 0 } } });
    expect(failing(clean.report)).toEqual([]);
    expect(clean.report.rules.map((rule) => rule.rule)).toEqual(["format", "gltf.validator.maxErrors", "gltf.validator.maxWarnings"]);
  });

  it("keeps the validator's verdict when Blender cannot import the file", async () => {
    const { report } = await judged("overrun.glb", PLAIN_SPEC);
    expect(report.failure).toMatchObject({ stage: "measure", code: "import_failed" });
    expect(report.rules.map((rule) => [rule.rule, rule.pass])).toEqual([
      ["measure", false],
      ["gltf.validator.maxErrors", false],
    ]);
    expect(report.validation?.issues.map((issue) => issue.code)).toContain("ACCESSOR_TOO_LONG");
  });

  it("allows a stated number of errors and warnings", async () => {
    const { report } = await judged("wrong-bounds.glb", { ...PLAIN_SPEC, gltf: { validator: { maxErrors: 3, maxWarnings: 0 } } });
    expect(failing(report)).toEqual([]);
  });

  it("fails the rule when the delivery is not glTF", async () => {
    copyFileSync(join(assets, "wrong-colour.blend"), join(assets, "box.blend"));
    const { report } = await judged("box.blend", PLAIN_SPEC);
    expect(failing(report)).toEqual(["format", "gltf.validator.maxErrors"]);
    expect(report.rules.find((rule) => rule.rule === "gltf.validator.maxErrors")?.measured).toBeNull();
    expect(report.validation).toBeNull();
    expect(report.summary).toContain("  glTF validator: no result");
  });
});

describe("what the validator may open", workBudget(120_000), () => {
  it("serves only files inside the asset folder", () => {
    const asset = join(assets, "external", "external.gltf");
    expect(resolveResource(asset, "base.png")).toEqual({ path: expect.stringMatching(/base\.png$/) });
    expect(resolveResource(asset, "https://example.com/base.png")).toEqual({ refused: REFUSAL_REASONS.scheme });
    expect(resolveResource(asset, "file:///etc/passwd")).toEqual({ refused: REFUSAL_REASONS.scheme });
    expect(resolveResource(asset, "/etc/passwd")).toEqual({ refused: REFUSAL_REASONS.absolute });
    expect(resolveResource(asset, "C%3A/Windows/win.ini")).toEqual({ refused: REFUSAL_REASONS.scheme });
    expect(resolveResource(asset, "../plain.glb")).toEqual({ refused: REFUSAL_REASONS.escape });
    expect(resolveResource(asset, "..%2Fplain.glb")).toEqual({ refused: REFUSAL_REASONS.escape });
    expect(resolveResource(asset, "nothing.png")).toEqual({ refused: "the file does not exist" });
    expect(resolveResource(asset, "%E0%A4%A")).toEqual({ refused: REFUSAL_REASONS.encoding });
    mkdirSync(join(assets, "external", "folder"), { recursive: true });
    expect(resolveResource(asset, "folder")).toEqual({ refused: "the URI is not a file" });
  });

  it("never opens a remote or outside image, and reports it as an error", async () => {
    for (const [name, uri] of [["remote.gltf", "http://127.0.0.1:9/base.png"], ["outside.gltf", "../plain.glb"]] as const) {
      const validation = await validateGltf(gltfWithImage(name, uri), "gltf", LIMITS);
      expect(validation.refused).toHaveLength(1);
      expect(validation.refused[0]?.startsWith(`${uri}: `)).toBe(true);
      expect(validation.issues.find((issue) => issue.code === "IO_ERROR")).toMatchObject({ severity: "error", pointer: "/images/0/uri" });
    }
  });

  it("stops at the size cap", async () => {
    await expect(validateGltf(join(assets, "textured.glb"), "glb", { ...LIMITS, maxBytes: 1000 })).rejects.toThrow(ValidationError);
    const capped = await validateGltf(join(assets, "external", "external.gltf"), "gltf", { ...LIMITS, maxBytes: 6000 });
    expect(capped.refused.length).toBeGreaterThan(0);
    expect(capped.refused.every((entry) => entry.includes("over its cap of 6000 bytes"))).toBe(true);
    expect(capped.bytes).toBeLessThanOrEqual(6000);
    const { report } = await judged("textured.glb", PLAIN_SPEC, { maxValidatorBytes: 1000 });
    expect(report.failure).toMatchObject({ stage: "validate", code: "too_large" });
    expect(report.rules[0]).toMatchObject({ rule: "validate", pass: false });
  });

  it("runs on every glTF delivery, writing validation.json even when the spec has no gltf rule", async () => {
    const { report, outDir } = await judged("wrong-bounds.glb", { format: "glb", views: ["front"] });
    expect(report.passed).toBe(true);
    expect("validation" in report).toBe(false);
    expect(JSON.parse(readFileSync(join(outDir, "validation.json"), "utf8"))).toMatchObject({ ok: true, errors: 3 });
    const capped = await judged("textured.glb", { format: "glb", views: ["front"] }, { maxValidatorBytes: 1000 });
    expect(capped.report.passed).toBe(true);
    expect(JSON.parse(readFileSync(join(capped.outDir, "validation.json"), "utf8"))).toMatchObject({ ok: false, error: { code: "too_large" } });
    const blend = await judged("wrong-colour.blend", { format: "blend", views: ["front"] });
    expect(existsSync(join(blend.outDir, "validation.json"))).toBe(false);
  });
});
