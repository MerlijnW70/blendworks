import { describe, expect, it } from "vitest";
import { analyse } from "../../src/package/analysis.js";
import { compareAnalyses, floatTolerance, quantisationTolerance, type Check } from "../../src/package/equivalence.js";
import { accessor, crate, document, primitive, quantisedCrate, scalar, type Json } from "./gltf-json.js";

const INFO = { totalTriangleCount: 18 };

function check(equivalence: { checks: Check[] }, name: string): Check {
  const found = equivalence.checks.find((entry) => entry.name === name);
  if (found === undefined) throw new Error(`no check named ${name}`);
  return found;
}

function compare(reference: Json, candidate: Json, tolerance = 1e-4, candidateInfo = INFO) {
  return compareAnalyses({ reference: analyse(reference), candidate: analyse(candidate), tolerance, referenceInfo: INFO, candidateInfo });
}

describe("reading a glTF document", () => {
  it("finds triangles, boxes and the named tree, folding unnamed dequantisation nodes into their named owner", () => {
    const plain = analyse(crate());
    expect(plain.paths).toEqual(["/Rig", "/Rig/Arm", "/Rig/Hand"]);
    expect(plain.triangles).toBe(12 + 6);
    const arm = plain.holders.find((holder) => holder.path === "/Rig/Arm");
    expect(arm?.localBox).toEqual({ min: [-1, -1, -1], max: [1, 1, 1] });
    expect(arm?.worldBox).toEqual({ min: [0, -1, -1], max: [2, 1, 1] });
    const hand = plain.holders.find((holder) => holder.path === "/Rig/Hand");
    expect(hand?.localBox).toEqual({ min: [0, 0, 0], max: [2, 1, 1] });
    expect(hand?.worldBox).toEqual({ min: [1, 2, 0], max: [3, 3, 1] });
    expect(plain.worldBox).toEqual({ min: [0, -1, -1], max: [3, 3, 1] });
    const packed = analyse(quantisedCrate());
    expect(packed.paths).toEqual(plain.paths);
    expect(packed.holders.map((holder) => holder.path)).toEqual(["/Rig/Arm", "/Rig/Hand"]);
    const [packedArm, packedHand] = packed.holders;
    for (const axis of [0, 1, 2]) expect(packedArm?.localBox?.min[axis]).toBeCloseTo(-1, 12);
    expect(packedHand?.localBox?.min[0]).toBeCloseTo(0, 12);
    expect(packedHand?.localBox?.max[0]).toBeCloseTo(2, 12);
    expect(packedHand?.localBox?.max[1]).toBeCloseTo(1, 12);
    expect(packed.worldBox?.max[1]).toBeCloseTo(3, 12);
  });

  it("decodes normalised integer positions and counts strips, fans and unindexed lists", () => {
    const normalised = document({
      nodes: [{ name: "n", mesh: 0 }],
      meshes: [{ primitives: [primitive(0, undefined, undefined), primitive(1, undefined, undefined, 5), primitive(1, 2, undefined, 6)] }],
      accessors: [accessor(6, [-32767, 0, 0], [32767, 0, 0], { componentType: 5122, normalized: true }), accessor(5, [0, 0, 0], [1, 1, 1]), scalar(7)],
    });
    const found = analyse(normalised);
    expect(found.holders[0]?.triangles).toBe(2 + 3 + 5);
    expect(found.holders[0]?.localBox).toEqual({ min: [-1, 0, 0], max: [1, 1, 1] });
  });

  it("reads texture slots through KTX2 sources and the UV set of each map", () => {
    const material = analyse({
      ...crate(),
      textures: [{ extensions: { KHR_texture_basisu: { source: 1 } } }, { source: 0 }],
    }).materials[0];
    expect(material?.slots).toEqual({ baseColor: { texCoord: 0, image: 1 }, normal: { texCoord: 1, image: 0 } });
  });
});

describe("tolerances", () => {
  it("is one quantisation step of the diagonal, and a float epsilon for unquantised data", () => {
    const box = { min: [0, 0, 0] as [number, number, number], max: [1, 1, 1] as [number, number, number] };
    expect(quantisationTolerance(box)).toBeCloseTo(Math.sqrt(3) / (2 ** 14 - 1), 12);
    expect(quantisationTolerance(box, 8)).toBeCloseTo(Math.sqrt(3) / 255, 12);
    expect(floatTolerance(box)).toBeCloseTo(Math.sqrt(3) * 1e-5, 12);
  });
});

describe("comparing a package with its compressed form", () => {
  it("accepts a quantised copy that holds the same tree, triangles, boxes and materials", () => {
    const result = compare(crate(), quantisedCrate());
    expect(result.checks.map((entry) => [entry.name, entry.pass])).toEqual([
      ["hierarchy", true],
      ["triangles", true],
      ["bounds", true],
      ["materials", true],
      ["validatorCounts", true],
    ]);
    expect(result.pass).toBe(true);
  });

  it("fails when the bounds move beyond the tolerance, and only the bounds check fails", () => {
    const moved = quantisedCrate();
    (moved.nodes as Json[])[3] = { mesh: 0, scale: [0.001, 0.001, 0.001], translation: [0, 0, 0.05] };
    const result = compare(crate(), moved);
    expect(result.pass).toBe(false);
    expect(result.checks.filter((entry) => !entry.pass).map((entry) => entry.name)).toEqual(["bounds"]);
    expect(check(result, "bounds").detail).toContain("/Rig/Arm differs by 0.05");
    expect(compare(crate(), moved, 0.06).pass).toBe(true);
  });

  it("fails when the whole asset box moves even if every node box agrees", () => {
    const shifted = quantisedCrate();
    (shifted.nodes as Json[])[0] = { name: "Rig", translation: [1.5, 0, 0], children: [1, 2] };
    const result = compare(crate(), shifted);
    expect(check(result, "bounds").pass).toBe(false);
    expect(check(result, "hierarchy").pass).toBe(false);
  });

  it("fails when a node is missing or a transform changes", () => {
    const renamed = crate();
    (renamed.nodes as Json[])[2] = { name: "Palm", translation: [0, 2, 0], mesh: 1 };
    expect(check(compare(crate(), renamed), "hierarchy").detail).toContain("missing /Rig/Hand");
    const turned = crate();
    (turned.nodes as Json[])[0] = { name: "Rig", translation: [1, 0.5, 0], children: [1, 2] };
    expect(check(compare(crate(), turned), "hierarchy").pass).toBe(false);
  });

  it("fails when triangles are lost", () => {
    const thinner = crate();
    (thinner.accessors as Json[])[3] = scalar(15);
    const result = compare(crate(), thinner, 1e-4, { totalTriangleCount: 17 });
    expect(check(result, "triangles").detail).toContain("/Rig/Hand has 6 against 5");
    expect(check(result, "triangles").pass).toBe(false);
  });

  it("fails when a material, a texture slot or a UV set changes", () => {
    const stripped = crate();
    (stripped.materials as Json[])[0] = { name: "steel", pbrMetallicRoughness: {} };
    expect(check(compare(crate(), stripped), "materials").detail).toContain("steel baseColor map is in only one file");
    const other = crate();
    (other.materials as Json[])[0] = { name: "steel", pbrMetallicRoughness: { baseColorTexture: { index: 0 } }, normalTexture: { index: 1, texCoord: 0 } };
    expect(check(compare(crate(), other), "materials").detail).toContain("steel normal uses UV set 1 against 0");
    const renamed = crate();
    (renamed.materials as Json[])[1] = { name: "gold", alphaMode: "BLEND", doubleSided: true };
    expect(check(compare(crate(), renamed), "materials").pass).toBe(false);
    const fewer = crate();
    fewer.images = [{ mimeType: "image/png", bufferView: 0 }];
    expect(check(compare(crate(), fewer), "materials").detail).toContain("2 images against 1");
  });

  it("cross-checks the validator's triangle count, allowing only a small quantisation loss", () => {
    const small = compare(crate(), quantisedCrate(), 1e-4, { totalTriangleCount: 18 });
    expect(check(small, "validatorCounts").pass).toBe(true);
    const lossy = compareAnalyses({ reference: analyse(crate()), candidate: analyse(crate()), tolerance: 1e-4, referenceInfo: INFO, candidateInfo: { totalTriangleCount: 17 } });
    expect(check(lossy, "validatorCounts").pass).toBe(false);
    const missing = compareAnalyses({ reference: analyse(crate()), candidate: analyse(crate()), tolerance: 1e-4, referenceInfo: INFO, candidateInfo: {} });
    expect(check(missing, "validatorCounts").detail).toContain("no triangle count");
    const more = compare(crate(), crate(), 1e-4, { totalTriangleCount: 19 });
    expect(check(more, "validatorCounts").detail).toContain("more than");
    const noted = compareAnalyses({ reference: analyse(crate()), candidate: analyse(bigCrate()), tolerance: 1e-4, referenceInfo: INFO, candidateInfo: { totalTriangleCount: 2000 } });
    expect(check(noted, "validatorCounts").pass).toBe(true);
    expect(check(noted, "validatorCounts").detail).toContain("6 triangles of the candidate collapse");
  });
});

function bigCrate(): Json {
  const big = crate();
  (big.accessors as Json[])[1] = scalar(6000);
  return big;
}
