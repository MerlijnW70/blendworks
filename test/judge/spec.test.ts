import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseSpec, SpecError, specJsonSchema } from "../../src/judge/spec.js";
import { BlenderVersionError, checkBlenderVersion, parseBlenderVersion } from "../../src/judge/version.js";
import { CRATE_SPEC } from "./helpers.js";

function problems(value: unknown): string[] {
  try {
    parseSpec(value);
  } catch (error) {
    if (error instanceof SpecError) return error.problems;
    throw error;
  }
  return [];
}

describe("the asset spec", () => {
  it("accepts every field of the design's example", () => {
    expect(parseSpec(CRATE_SPEC)).toEqual(CRATE_SPEC);
  });

  it("needs only format", () => {
    expect(parseSpec({ format: "blend" })).toEqual({ format: "blend" });
    expect(problems({ name: "crate" })).toEqual(["format: Invalid option: expected one of \"glb\"|\"gltf\"|\"fbx\"|\"obj\"|\"blend\""]);
  });

  it("names the field of every problem", () => {
    const found = problems({
      format: "stl",
      triangles: { max: 1.5 },
      size: { x: [2, 1] },
      uv: { maxOverlap: 2 },
      views: ["front", "front", "under"],
      colour: "red",
    });
    expect(found.some((problem) => problem.startsWith("format:"))).toBe(true);
    expect(found.some((problem) => problem.startsWith("triangles.max:"))).toBe(true);
    expect(found).toContain("size.x: the first number (minimum) must not exceed the second (maximum)");
    expect(found.some((problem) => problem.startsWith("uv.maxOverlap:"))).toBe(true);
    expect(found.some((problem) => problem.startsWith("views.2:"))).toBe(true);
    expect(found.some((problem) => problem.includes("colour"))).toBe(true);
  });

  it("refuses a minimum over its maximum and repeated views", () => {
    expect(problems({ format: "glb", materials: { min: 3, max: 1 } })).toEqual(["materials: min must not exceed max"]);
    expect(problems({ format: "glb", views: ["top", "top"] })).toEqual(["views: views must not repeat"]);
  });

  it("is published as the JSON Schema in schemas/asset-spec.schema.json", () => {
    const published = JSON.parse(readFileSync("schemas/asset-spec.schema.json", "utf8"));
    expect(published).toEqual(specJsonSchema());
    expect(published.required).toEqual(["format"]);
    expect(published.additionalProperties).toBe(false);
  });
});

describe("the Blender version check", () => {
  it("accepts 5.2 and refuses the others", () => {
    expect(checkBlenderVersion("Blender 5.2.3 LTS (hash e13b728c6880)\n")).toBe("5.2.3");
    expect(() => checkBlenderVersion("Blender 4.2.1 LTS\n")).toThrow(BlenderVersionError);
    expect(() => checkBlenderVersion("Blender 5.3.0\n")).toThrow("needs Blender 5.2");
    expect(() => checkBlenderVersion("Python 3.13\n")).toThrow("cannot read the Blender version");
    expect(parseBlenderVersion("Read prefs\nBlender 5.2.0\n")).toBe("5.2.0");
  });
});
