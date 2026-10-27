import { createHash } from "node:crypto";
import { copyFileSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { fbxTextures } from "../../src/judge/fbx.js";
import type { Report } from "../../src/judge/report.js";
import { judge, type JudgeOptions } from "../../src/judge/run.js";
import { freshDir, makeFixtures, makeFixtureSet, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let crates = "";
let integrity = "";
let work = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets: crates } = makeFixtures("delivery"));
  ({ assets: integrity } = makeFixtureSet("integrity_fixtures", "delivery-integrity"));
  work = freshDir("delivery", "work");
}));

function sha256(data: Buffer | string): string {
  return createHash("sha256").update(data).digest("hex");
}

function judged(name: string, assetPath: string, overrides: Record<string, unknown> = {}, options: Partial<JudgeOptions> = {}): Promise<Report> {
  const spec = writeSpec(work, name, { views: ["front"], ...overrides });
  return judge({ specPath: spec, assetPath, outDir: freshDir("delivery", "reports", name), preview: true, ...options });
}

describe("the judge judges a private copy", workBudget(180_000), () => {
  it("is not affected when the original changes after the copy, and records the hash of what it judged", async () => {
    const original = join(work, "crate.glb");
    copyFileSync(join(crates, "crate.glb"), original);
    const before = readFileSync(original);
    const report = await judged("swapped", original, {}, { afterCopy: () => copyFileSync(join(crates, "wrong-size.glb"), original) });
    expect(readFileSync(original).equals(before)).toBe(false);
    expect(report.passed).toBe(true);
    expect(report.measurements?.size).toEqual([1, 1, 0.8]);
    expect(report.asset.sha256).toBe(sha256(before));
    expect(report.asset.files).toEqual([{ path: "crate.glb", bytes: before.length, sha256: sha256(before) }]);
    expect(report.asset.setSha256).toBe(sha256(`${sha256(before)}  crate.glb\n`));
  });

  it("counts the OBJ, its MTL and the texture the MTL names in fileSize, and hashes all three", async () => {
    const files = ["textured.mtl", "textured.obj", "wood.png"];
    const sizes = files.map((name) => statSync(join(integrity, name)).size);
    const total = sizes.reduce((sum, size) => sum + size, 0);
    const report = await judged("obj-set", join(integrity, "textured.obj"), { format: "obj", fileSize: { maxBytes: total }, selfContained: true });
    expect(report.passed).toBe(true);
    expect(report.measurements?.fileBytes).toBe(total);
    expect(report.asset.files.map((file) => [file.path, file.bytes])).toEqual(files.map((name, index) => [name, sizes[index]]));
    expect(report.measurements?.references).toEqual({ files: 2, unresolved: [] });
    const tight = await judged("obj-tight", join(integrity, "textured.obj"), { format: "obj", fileSize: { maxBytes: total - 1 } });
    expect(tight.rules.filter((rule) => !rule.pass).map((rule) => rule.rule)).toEqual(["fileSize.maxBytes"]);
  });

  it("copies an FBX's texture beside it, and fails selfContained for an FBX whose texture is missing", async () => {
    const textured = await judged("fbx-set", join(integrity, "textured.fbx"), { format: "fbx", selfContained: true });
    expect(textured.passed).toBe(true);
    expect(textured.asset.files.map((file) => file.path)).toEqual(["textured.fbx", "wood.png"]);
    const embedded = await judged("fbx-embedded", join(integrity, "embedded.fbx"), { format: "fbx", selfContained: true });
    expect(embedded.passed).toBe(true);
    expect(embedded.asset.files.map((file) => file.path)).toEqual(["embedded.fbx"]);
    const missing = await judged("fbx-missing", join(integrity, "missing.fbx"), { format: "fbx", selfContained: true });
    expect(missing.rules.filter((rule) => !rule.pass).map((rule) => rule.rule)).toEqual(["selfContained"]);
    expect(missing.measurements?.references.unresolved).toEqual(["texture missing.png: the file is not in the asset folder"]);
    const lenient = await judged("fbx-missing-lenient", join(integrity, "missing.fbx"), { format: "fbx" });
    expect(lenient.passed).toBe(true);
    expect(lenient.summary).toContain("unresolved references: texture missing.png: the file is not in the asset folder");
  });

  it("reads texture names from binary FBX records and from Video content", () => {
    const textures = fbxTextures(readFileSync(join(integrity, "textured.fbx")));
    expect(textures.some((texture) => texture.names.some((name) => name.endsWith("wood.png")) && !texture.embedded)).toBe(true);
    const embedded = fbxTextures(readFileSync(join(integrity, "embedded.fbx")));
    expect(embedded.some((texture) => texture.embedded)).toBe(true);
  });
});

describe("importer limits before Blender evaluates anything", workBudget(180_000), () => {
  function gltfVariant(name: string, change: (document: Record<string, any>) => void): string {
    const document = JSON.parse(readFileSync(join(crates, "crate.gltf"), "utf8"));
    change(document);
    copyFileSync(join(crates, "crate.bin"), join(work, "crate.bin"));
    writeFileSync(join(work, name), JSON.stringify(document));
    return join(work, name);
  }

  it("refuses a glTF whose accessors claim 50 million triangles before import", async () => {
    const asset = gltfVariant("claims.gltf", (document) => {
      const primitives = document.meshes[0].primitives as { indices: number }[];
      for (const primitive of primitives) document.accessors[primitive.indices].count = 150_000_000 / primitives.length;
    });
    const report = await judged("claims", asset, { format: "gltf" });
    expect(report.failure).toMatchObject({ stage: "measure", code: "too_many_triangles" });
    expect(report.failure?.message).toBe("the glTF declares 50000000 triangles in its accessors, over the judge's cap of 2000000; refused before import");
  });

  it("refuses an image whose header claims 40000 x 40000 pixels, and a required meshopt extension", async () => {
    const header = Buffer.alloc(64);
    Buffer.from("89504e470d0a1a0a0000000d49484452", "hex").copy(header);
    header.writeUInt32BE(40_000, 16);
    header.writeUInt32BE(40_000, 20);
    writeFileSync(join(work, "huge.png"), header);
    const image = await judged("huge-image", gltfVariant("huge.gltf", (document) => {
      document.images = [{ uri: "huge.png" }];
    }), { format: "gltf" });
    expect(image.failure).toMatchObject({ stage: "measure", code: "image_too_large" });
    expect(image.failure?.message).toBe("glTF image 0 is 40000 x 40000 pixels, over the judge's limit of 16384 per side");
    const meshopt = await judged("meshopt", gltfVariant("meshopt.gltf", (document) => {
      document.extensionsUsed = ["EXT_meshopt_compression"];
      document.extensionsRequired = ["EXT_meshopt_compression"];
    }), { format: "gltf" });
    expect(meshopt.failure).toMatchObject({ stage: "measure", code: "unsupported_extension" });
  });

  it("refuses modifiers that multiply geometry past the cap, and geometry nodes it cannot bound", async () => {
    const arrays = await judged("array-bomb", join(integrity, "array-bomb.blend"), { format: "blend" });
    expect(arrays.failure).toMatchObject({ stage: "measure", code: "too_many_triangles" });
    expect(arrays.failure?.message).toContain("may make up to 12000000 triangles");
    const nodes = await judged("geometry-nodes", join(integrity, "geometry-nodes.blend"), { format: "blend" });
    expect(nodes.failure).toMatchObject({ stage: "measure", code: "unbounded_geometry" });
    expect(nodes.failure?.message).toContain("nodes modifier Nodes cannot be bounded before it runs");
  });
});
