import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Measurements } from "../../src/judge/measurements.js";
import { summarize, type Report } from "../../src/judge/report.js";
import { evaluateRules } from "../../src/judge/rules.js";
import { parseSpec, SpecError, specJsonSchema } from "../../src/judge/spec.js";
import type { Validation } from "../../src/judge/validator.js";
import { CRATE_SPEC } from "./helpers.js";

const NONE = { count: 0, names: [] };

const TEXTURES: NonNullable<Measurements["textures"]> = {
  count: 2,
  gpuBytes: 2 * 89_478_484,
  smallestSide: 4096,
  largestSide: 4096,
  images: [],
  materials: [
    { name: "hickory", maps: ["baseColor", "metallicRoughness", "normal"] },
    { name: "steel", maps: ["baseColor", "metallicRoughness"] },
  ],
  facesWithoutMaterial: false,
  missing: { baseColor: NONE, metallicRoughness: NONE, normal: { count: 1, names: ["steel"] }, emissive: { count: 2, names: ["hickory", "steel"] }, occlusion: { count: 2, names: ["hickory", "steel"] } },
  external: NONE,
  nonPowerOfTwo: NONE,
  colourSpaceMismatches: { count: 0, items: [] },
};

const CRATE: Measurements = {
  format: "glb",
  fileBytes: 2784,
  triangles: 12,
  objects: 1,
  objectsAll: 1,
  bounds: { min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] },
  size: [1, 1, 0.8],
  origin: { point: [0, 0, 0], source: "object Crate", bottomCentreDistance: 0, centreDistance: 0.4 },
  manifold: { nonManifoldEdges: 0, boundaryEdges: 0, wireEdges: 0, nonManifoldVertices: 0, looseVertices: 0, looseParts: 1 },
  materials: { count: 2, names: ["hickory", "steel"] },
  uv: { present: true, meshesWithoutUv: 0, coverage: 0.375, overlap: 0 },
  externalFilesRefused: [],
};

const VALIDATION: Validation = { validator: "2.0.0-dev.3.10", seconds: 0.1, bytes: 2784, errors: 0, warnings: 2, infos: 0, hints: 0, issues: [], refused: [] };

function results(rules: Record<string, unknown>, measurements: Measurements, validation: Validation | null = VALIDATION) {
  return evaluateRules(parseSpec({ format: "glb", ...rules }), measurements, validation).slice(1);
}

function problems(value: unknown): string[] {
  try {
    parseSpec(value);
  } catch (error) {
    if (error instanceof SpecError) return error.problems;
    throw error;
  }
  return [];
}

function report(rules: Report["rules"], measurements: Measurements, validation?: Validation | null): Omit<Report, "summary"> {
  return {
    passed: false,
    preview: false,
    spec: { path: "spec.json", sha256: null, name: "pickaxe" },
    asset: { path: "pickaxe.glb", sha256: null, bytes: 1 },
    blender: "5.2.3",
    sandbox: null,
    renderSandbox: null,
    device: null,
    failure: null,
    rules,
    measurements,
    renders: null,
    timings: { measure: null, device: null, render: null, sheet: null, total: 0 },
    ...(validation === undefined ? {} : { validation }),
  };
}

describe("the texture, validator and floating-part rules in a spec", () => {
  it("accepts the design's example and publishes the new fields in the JSON Schema", () => {
    const example = {
      format: "glb",
      textures: { required: ["baseColor", "metallicRoughness", "normal"], minSize: 512, maxSize: 4096, embedded: true, maxCount: 3, maxGpuBytes: 268_435_456, powerOfTwo: true },
      gltf: { validator: { maxErrors: 0, maxWarnings: 10 } },
      parts: { maxFloating: 0, tolerance: 0.001 },
    };
    expect(parseSpec(example)).toEqual(example);
    const properties = (specJsonSchema() as { properties: Record<string, unknown> }).properties;
    expect(Object.keys(properties)).toEqual(expect.arrayContaining(["textures", "gltf", "parts"]));
    const blocks = readFileSync("docs/DESIGN.md", "utf8").split("```json\n").slice(1).map((block) => block.split("\n```")[0] ?? "");
    const documented = blocks.find((block) => block.includes('"textures"'));
    expect(parseSpec(JSON.parse(documented ?? "null"))).toEqual(example);
  });

  it("refuses rules that cannot hold", () => {
    expect(problems({ format: "fbx", gltf: { validator: {} } })).toEqual(["gltf: the gltf rules need format glb or gltf"]);
    expect(problems({ format: "glb", textures: { minSize: 1024, maxSize: 512 } })).toEqual(["textures: minSize must not exceed maxSize"]);
    expect(problems({ format: "glb", textures: { required: ["normal", "normal"] } })).toEqual(["textures.required: map kinds must not repeat"]);
    expect(problems({ format: "glb", textures: { required: ["height"] } })[0]).toMatch(/^textures\.required\.0: /);
    expect(problems({ format: "glb", textures: { required: [] } })[0]).toMatch(/^textures\.required: /);
    expect(problems({ format: "glb", textures: { minSize: 0 } })[0]).toMatch(/^textures\.minSize: /);
    expect(problems({ format: "glb", parts: { tolerance: 0.001 } })[0]).toMatch(/^parts\.maxFloating: /);
    expect(problems({ format: "glb", parts: { maxFloating: 0, tolerance: 2 } })[0]).toMatch(/^parts\.tolerance: /);
    expect(problems({ format: "glb", gltf: { validator: { maxErrors: -1 } } })[0]).toMatch(/^gltf\.validator\.maxErrors: /);
    expect(problems({ format: "glb", gltf: {} })[0]).toMatch(/^gltf\.validator: /);
  });
});

describe("evaluating the new rules", () => {
  it("names the materials that lack a required map kind", () => {
    const measured = { ...CRATE, textures: TEXTURES };
    expect(results({ textures: { required: ["baseColor", "metallicRoughness"] } }, measured)).toEqual([
      { rule: "textures.required", measured: { materials: 2, missing: [] }, limit: ["baseColor", "metallicRoughness"], pass: true },
    ]);
    expect(results({ textures: { required: ["normal", "emissive"] } }, measured)[0]).toEqual({
      rule: "textures.required",
      measured: { materials: 2, missing: ["normal: steel", "emissive: hickory, steel"] },
      limit: ["normal", "emissive"],
      pass: false,
    });
    const crowded = { ...TEXTURES, missing: { ...TEXTURES.missing, normal: { count: 70, names: ["a", "b"] } } };
    expect(results({ textures: { required: ["normal"] } }, { ...CRATE, textures: crowded })[0]?.measured).toEqual({ materials: 2, missing: ["normal: a, b and 68 more"] });
  });

  it("includes both ends of the size, count and GPU limits", () => {
    const measured = { ...CRATE, textures: TEXTURES };
    const exact = { minSize: 4096, maxSize: 4096, maxCount: 2, maxGpuBytes: 178_956_968 };
    expect(results({ textures: exact }, measured).map((rule) => rule.pass)).toEqual([true, true, true, true]);
    const tight = [{ minSize: 4097 }, { maxSize: 4095 }, { maxCount: 1 }, { maxGpuBytes: 178_956_967 }];
    expect(tight.flatMap((textures) => results({ textures }, measured)).map((rule) => [rule.rule, rule.measured, rule.pass])).toEqual([
      ["textures.minSize", 4096, false],
      ["textures.maxSize", 4096, false],
      ["textures.maxCount", 2, false],
      ["textures.maxGpuBytes", 178_956_968, false],
    ]);
  });

  it("passes size limits with no images, but fails every texture rule when textures were not measured", () => {
    const bare = { ...TEXTURES, count: 0, gpuBytes: 0, smallestSide: null, largestSide: null };
    const rules = { textures: { minSize: 16, maxSize: 64, embedded: true, maxCount: 0, maxGpuBytes: 0, powerOfTwo: true } };
    expect(results(rules, { ...CRATE, textures: bare }).every((rule) => rule.pass)).toBe(true);
    const unmeasured = results({ textures: { ...rules.textures, required: ["normal"] } }, CRATE);
    expect(unmeasured.map((rule) => [rule.rule, rule.measured, rule.pass])).toEqual([
      ["textures.required", null, false],
      ["textures.minSize", null, false],
      ["textures.maxSize", null, false],
      ["textures.embedded", null, false],
      ["textures.maxCount", null, false],
      ["textures.maxGpuBytes", null, false],
      ["textures.powerOfTwo", null, false],
    ]);
  });

  it("checks embedded and power-of-two only when they are true", () => {
    const measured = { ...CRATE, textures: { ...TEXTURES, external: { count: 1, names: ["bark (bark.png)"] }, nonPowerOfTwo: { count: 1, names: ["bark 48x20"] } } };
    expect(results({ textures: { embedded: false, powerOfTwo: false } }, measured)).toEqual([]);
    expect(results({ textures: { embedded: true, powerOfTwo: true } }, measured)).toEqual([
      { rule: "textures.embedded", measured: { external: 1, images: ["bark (bark.png)"] }, limit: { external: 0 }, pass: false },
      { rule: "textures.powerOfTwo", measured: { nonPowerOfTwo: 1, images: ["bark 48x20"] }, limit: { nonPowerOfTwo: 0 }, pass: false },
    ]);
  });

  it("allows 0 validator errors by default and compares warnings only when a limit is set", () => {
    expect(results({ gltf: { validator: {} } }, CRATE)).toEqual([{ rule: "gltf.validator.maxErrors", measured: 0, limit: 0, pass: true }]);
    expect(results({ gltf: { validator: { maxWarnings: 1 } } }, CRATE)[1]).toEqual({ rule: "gltf.validator.maxWarnings", measured: 2, limit: 1, pass: false });
    expect(results({ gltf: { validator: {} } }, CRATE, { ...VALIDATION, errors: 1 })[0]?.pass).toBe(false);
    expect(results({ gltf: { validator: { maxWarnings: 5 } } }, CRATE, null).map((rule) => [rule.measured, rule.pass])).toEqual([
      [null, false],
      [null, false],
    ]);
  });

  it("compares the floating parts with maxFloating, and fails when they were not measured", () => {
    const floating = { tolerance: 0.001, parts: 3, count: 1, items: [{ object: "Lamp", index: 0, bounds: { min: [0, 0, 1] as [number, number, number], max: [1, 1, 2] as [number, number, number] } }] };
    expect(results({ parts: { maxFloating: 1 } }, { ...CRATE, floating })).toEqual([
      { rule: "parts.maxFloating", measured: { floating: 1, parts: ["Lamp part 0"], tolerance: 0.001 }, limit: 1, pass: true },
    ]);
    expect(results({ parts: { maxFloating: 0 } }, { ...CRATE, floating })[0]?.pass).toBe(false);
    expect(results({ parts: { maxFloating: 0 } }, { ...CRATE, floating: { ...floating, count: 65 } })[0]?.measured).toMatchObject({ parts: ["Lamp part 0", "and 64 more"] });
    expect(results({ parts: { maxFloating: 5 } }, CRATE)).toEqual([{ rule: "parts.maxFloating", measured: null, limit: 5, pass: false }]);
  });
});

describe("old specs", () => {
  it("give the same rules and summary when the new measurements are present", () => {
    const spec = parseSpec(CRATE_SPEC);
    const floating = { tolerance: 0.001, parts: 1, count: 0, items: [] };
    const plain = evaluateRules(spec, CRATE);
    expect(evaluateRules(spec, { ...CRATE, textures: TEXTURES, floating }, VALIDATION)).toEqual(plain);
    expect(plain.map((rule) => rule.rule)).toEqual(["format", "triangles.max", "size.x", "size.y", "size.z", "origin", "manifold", "materials.min", "materials.max", "uv.required", "uv.maxOverlap", "objects.max", "fileSize.maxBytes"]);
    const text = summarize(report(plain, CRATE));
    expect(text).not.toMatch(/textures|validator|colour/);
    expect(text.split("\n")).toHaveLength(16);
  });
});

describe("the summary of the new rules", () => {
  it("says at least or at most for every new limit", () => {
    const measured = { ...CRATE, textures: { ...TEXTURES, colourSpaceMismatches: { count: 2, items: [{ image: "normal", kind: "normal" as const, colourSpace: "sRGB", expected: "Non-Color" }] } } };
    const rules = results({ textures: { minSize: 512, maxSize: 4096, maxCount: 3, maxGpuBytes: 268_435_456 }, gltf: { validator: { maxWarnings: 2 } } }, measured);
    const validation = { ...VALIDATION, errors: 1, issues: [{ code: "ACCESSOR_VECTOR3_NON_UNIT", severity: "error" as const, pointer: "/meshes/2", message: "not of unit length: 0." }], refused: ["http://x/a.png: the URI has a scheme or an absolute path"] };
    const text = summarize(report(rules, measured, validation));
    expect(text).toContain("textures.minSize            measured 4096; required at least 512");
    expect(text).toContain("textures.maxSize            measured 4096; required at most 4096");
    expect(text).toContain("textures.maxCount           measured 2; required at most 3");
    expect(text).toContain("textures.maxGpuBytes        measured 178956968; required at most 268435456");
    expect(text).toContain("gltf.validator.maxWarnings  measured 2; required at most 2");
    expect(text).toContain("  textures: 2 images, GPU estimate 178956968 bytes (170.7 MiB, RGBA8 with mips)");
    expect(text).toContain("  colour spaces: 2 wrong\n    normal as normal is sRGB, expected Non-Color\n    and 1 more");
    expect(text).toContain("  glTF validator 2.0.0-dev.3.10: 1 errors, 2 warnings, 0 infos, 0 hints\n    error ACCESSOR_VECTOR3_NON_UNIT at /meshes/2: not of unit length: 0.");
    expect(text).toContain("    not opened: http://x/a.png: the URI has a scheme or an absolute path");
  });
});
