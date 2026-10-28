import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { blendReferences } from "../../src/judge/blend-refs.js";
import { fbxTextures } from "../../src/judge/fbx.js";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const NO_BLENDER = join("no-such-folder", "blender-that-never-starts");

let fixtures = "";
let work = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets: fixtures } = makeFixtureSet("external_fixtures", "external-references"));
  work = freshDir("external-references", "work");
  mkdirSync(join(work, "host"), { recursive: true });
  writeFileSync(join(work, "host", "secret.png"), "a file beside the delivery");
}));

function judgedWithoutBlender(asset: string, format: string): Promise<Report> {
  const name = asset.replace(/\W+/g, "-");
  const spec = writeSpec(work, name, { format, views: ["front"] });
  return judge({ specPath: spec, assetPath: asset, outDir: freshDir("external-references", "reports", name), blender: NO_BLENDER, preview: true });
}

async function refusedBeforeBlender(asset: string, format: string, fragment: string | RegExp): Promise<void> {
  const report = await judgedWithoutBlender(asset, format);
  expect(report.passed).toBe(false);
  expect(report.failure, asset).toMatchObject({ stage: "asset", code: "external_reference" });
  if (typeof fragment === "string") expect(report.failure?.message).toContain(fragment);
  else expect(report.failure?.message).toMatch(fragment);
  expect(report.blender).toBeNull();
}

async function passesTheCheck(asset: string, format: string): Promise<void> {
  const report = await judgedWithoutBlender(asset, format);
  expect(report.failure, asset).toMatchObject({ stage: "blender" });
}

function delivery(name: string, files: Record<string, string>): string {
  const folder = join(work, name);
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(join(folder, path, ".."), { recursive: true });
    writeFileSync(join(folder, path), text);
  }
  return join(folder, Object.keys(files)[0]!);
}

const CUBE_OBJ = "v 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl painted\nf 1 2 3\n";

function asciiFbx(texture: string): string {
  return `; FBX 7.4.0 project file\nFBXHeaderExtension:  {\n}\nObjects:  {\n${texture}\n}\n`;
}

function gltf(buffers: unknown[], images: unknown[] = []): string {
  return JSON.stringify({ asset: { version: "2.0" }, buffers, images });
}

describe("references refused before Blender starts", workBudget(120_000), () => {
  it("OBJ material libraries that are absolute or UNC", async () => {
    await refusedBeforeBlender(delivery("obj-absolute", { "crate.obj": `mtllib /etc/blendworks-secret.mtl\n${CUBE_OBJ}` }), "obj", "mtllib /etc/blendworks-secret.mtl: the reference is an absolute or UNC path");
    await refusedBeforeBlender(delivery("obj-unc", { "crate.obj": `mtllib \\\\judge-host\\share\\crate.mtl\n${CUBE_OBJ}` }), "obj", "the reference is an absolute or UNC path");
  });

  it("MTL maps with a drive, or that leave the folder behind their options", async () => {
    const drive = delivery("mtl-drive", { "crate.obj": `mtllib crate.mtl\n${CUBE_OBJ}`, "crate.mtl": "newmtl painted\nmap_Kd C:\\host\\secret.png\n" });
    await refusedBeforeBlender(drive, "obj", "map_Kd C:\\host\\secret.png in crate.mtl: the reference has a scheme, a drive or a stream name");
    const escape = delivery("mtl-escape", { "crate.obj": `mtllib crate.mtl\n${CUBE_OBJ}`, "crate.mtl": "newmtl painted\nmap_Kd -s 1 1 1 -bm 0.5 ../host/secret.png\n" });
    await refusedBeforeBlender(escape, "obj", "map_Kd ../host/secret.png in crate.mtl: the reference leaves the asset folder");
    const nested = delivery("mtl-nested", { "crate.obj": `mtllib materials/crate.mtl\n${CUBE_OBJ}`, "materials/crate.mtl": "newmtl painted\nmap_Kd ../wood.png\n", "wood.png": "png" });
    await passesTheCheck(nested, "obj");
  });

  it("binary FBX textures with an absolute path or one that leaves the folder", async () => {
    await refusedBeforeBlender(join(fixtures, "delivery", "absolute.fbx"), "fbx", /texture .*secret\.png: the reference (is an absolute or UNC path|has a scheme, a drive or a stream name)/);
    await refusedBeforeBlender(join(fixtures, "delivery", "escaping.fbx"), "fbx", "the reference leaves the asset folder");
    await passesTheCheck(join(fixtures, "delivery", "inside.fbx"), "fbx");
  });

  it("ASCII FBX textures: an escaping relative name, a UNC file name, and a bare name that is a path", async () => {
    const relative = asciiFbx('\tTexture: 2000, "Texture::wood", "" {\n\t\tFileName: "wood.png"\n\t\tRelativeFilename: "..\\host\\secret.png"\n\t}');
    await refusedBeforeBlender(delivery("fbx-ascii-escape", { "crate.fbx": relative }), "fbx", "the reference leaves the asset folder");
    const unc = asciiFbx('\tVideo: 3000, "Video::wood", "Clip" {\n\t\tFilename: "\\\\judge-host\\share\\secret.png"\n\t}');
    await refusedBeforeBlender(delivery("fbx-ascii-unc", { "crate.fbx": unc }), "fbx", "the reference is an absolute or UNC path");
    const named = asciiFbx('\tTexture: 2000, "Texture::/etc/blendworks-secret.png", "" {\n\t\tType: "TextureVideoClip"\n\t}');
    await refusedBeforeBlender(delivery("fbx-ascii-name", { "crate.fbx": named }), "fbx", "the reference is an absolute or UNC path");
    expect(fbxTextures(Buffer.from(relative)).map((texture) => texture.opened)).toEqual(["..\\host\\secret.png"]);
  });

  it("glTF buffers and images that are absolute, UNC, remote, on a drive or encoded to leave the folder", async () => {
    const cases: [string, string, string][] = [
      ["gltf-absolute", "/etc/blendworks-secret.bin", "the reference is an absolute or UNC path"],
      ["gltf-unc", "%5C%5Cjudge-host%5Cshare%5Csecret.bin", "the reference is an absolute or UNC path"],
      ["gltf-remote", "https://judge-host.invalid/secret.bin", "the reference has a scheme, a drive or a stream name"],
      ["gltf-drive", "C:%5Chost%5Csecret.bin", "the reference has a scheme, a drive or a stream name"],
      ["gltf-encoded", "%2e%2e%2fhost%2fsecret.bin", "the reference leaves the asset folder"],
    ];
    for (const [name, uri, reason] of cases) await refusedBeforeBlender(delivery(name, { "crate.gltf": gltf([{ uri, byteLength: 4 }]) }), "gltf", reason);
    await refusedBeforeBlender(delivery("gltf-image", { "crate.gltf": gltf([], [{ uri: "..%5Chost%5Csecret.png" }]) }), "gltf", "images[0]");
  });

  it(".blend image paths that are absolute, UNC or leave the folder, compressed or not, and linked libraries", async () => {
    for (const name of ["absolute-image", "compressed-absolute-image", "unc-image", "escaping-image", "linked-library"]) {
      await refusedBeforeBlender(join(fixtures, "delivery", `${name}.blend`), "blend", name === "linked-library" ? "library " : "image secret");
    }
    await passesTheCheck(join(fixtures, "delivery", "packed-image.blend"), "blend");
  });

  it("reads every image and library path from the .blend type table, and skips packed images", () => {
    const paths = (name: string) => blendReferences(readFileSync(join(fixtures, "delivery", `${name}.blend`))).map((entry) => [entry.kind, entry.path]);
    expect(paths("unc-image")).toEqual([["image", "\\\\judge-host\\share\\secret.png"]]);
    expect(paths("escaping-image")).toEqual([["image", "//../secret.png"]]);
    expect(paths("compressed-absolute-image")).toEqual(paths("absolute-image"));
    expect(paths("linked-library").map(([kind]) => kind)).toEqual(["library"]);
    expect(paths("packed-image")).toEqual([]);
  });
});
