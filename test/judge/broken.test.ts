import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { main } from "../../src/judge/cli.js";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";

useBlenderSlot();

let assets = "";
let work = "";

beforeAll(() => {
  ({ assets } = makeFixtures("broken"));
  work = freshDir("broken", "work");
}, 180_000);

async function judged(asset: string, overrides: Record<string, unknown> = {}, limits: Record<string, number> = {}): Promise<Report> {
  const name = asset.replace(/\W+/g, "-");
  const spec = writeSpec(work, name, { views: ["front"], ...overrides });
  const outDir = freshDir("broken", "reports", name);
  const report = await judge({ specPath: spec, assetPath: join(work, asset), outDir, ...limits });
  expect(JSON.parse(readFileSync(join(outDir, "report.json"), "utf8")).passed).toBe(report.passed);
  expect(readFileSync(join(outDir, "summary.txt"), "utf8")).toContain("FAIL");
  return report;
}

function failure(report: Report) {
  expect(report.passed).toBe(false);
  expect(report.rules[0]?.pass).toBe(false);
  return report.failure;
}

describe("broken deliveries fail cleanly with a reason", { timeout: 120_000 }, () => {
  it("a missing file", async () => {
    expect(failure(await judged("nothing-here.glb"))).toMatchObject({ stage: "asset", code: "missing" });
  });

  it("an empty file", async () => {
    writeFileSync(join(work, "empty.glb"), "");
    expect(failure(await judged("empty.glb"))).toMatchObject({ stage: "asset", code: "empty" });
  });

  it("a format the judge does not read", async () => {
    writeFileSync(join(work, "crate.stl"), "solid crate\nendsolid crate\n");
    expect(failure(await judged("crate.stl"))).toMatchObject({ stage: "asset", code: "unsupported_format" });
  });

  it("random bytes named .glb", async () => {
    writeFileSync(join(work, "noise.glb"), Buffer.from(Array.from({ length: 4096 }, (_, index) => (index * 7919) % 251)));
    expect(failure(await judged("noise.glb"))).toMatchObject({ stage: "measure", code: "corrupt" });
  });

  it("a glTF binary cut off half way", async () => {
    const whole = readFileSync(join(assets, "crate.glb"));
    writeFileSync(join(work, "cut.glb"), whole.subarray(0, Math.floor(whole.length / 2)));
    expect(failure(await judged("cut.glb"))).toMatchObject({ stage: "measure", code: "corrupt" });
  });

  it("a .blend cut off half way", async () => {
    const whole = readFileSync(join(assets, "crate.blend"));
    writeFileSync(join(work, "cut.blend"), whole.subarray(0, Math.floor(whole.length / 2)));
    expect(failure(await judged("cut.blend", { format: "blend" }))?.stage).toBe("measure");
  });

  it("an .obj with no geometry", async () => {
    writeFileSync(join(work, "blank.obj"), "o nothing\n");
    expect(failure(await judged("blank.obj", { format: "obj" }))).toMatchObject({ stage: "measure", code: "no_geometry" });
  });

  it("a .gltf that points at a file outside its folder", async () => {
    const document = JSON.parse(readFileSync(join(assets, "crate.gltf"), "utf8"));
    document.buffers[0].uri = "../assets/crate.bin";
    writeFileSync(join(work, "escape.gltf"), JSON.stringify(document));
    expect(failure(await judged("escape.gltf", { format: "gltf" }))).toMatchObject({ stage: "measure", code: "external_reference" });
  });

  it("a .gltf that points at an absolute path", async () => {
    const document = JSON.parse(readFileSync(join(assets, "crate.gltf"), "utf8"));
    document.buffers[0].uri = join(assets, "crate.bin");
    writeFileSync(join(work, "absolute.gltf"), JSON.stringify(document));
    expect(failure(await judged("absolute.gltf", { format: "gltf" }))).toMatchObject({ stage: "measure", code: "external_reference" });
  });

  it("a mesh over the triangle cap after its modifiers run", async () => {
    copyFileSync(join(assets, "over-budget.blend"), join(work, "over-budget.blend"));
    const report = await judged("over-budget.blend", { format: "blend" }, { maxTriangles: 100 });
    expect(failure(report)).toMatchObject({ stage: "measure", code: "too_many_triangles" });
    expect(report.failure?.message).toContain("more than 100 triangles");
  });

  it("a mesh whose modifiers guarantee more triangles than the cap, refused before they run", async () => {
    copyFileSync(join(assets, "over-budget.blend"), join(work, "over-budget-early.blend"));
    const report = await judged("over-budget-early.blend", { format: "blend" }, { maxTriangles: 50 });
    expect(failure(report)).toMatchObject({ stage: "measure", code: "too_many_triangles" });
    expect(report.failure?.message).toContain("at least 96 triangles");
  });

  it("a file over the size cap", async () => {
    copyFileSync(join(assets, "crate.glb"), join(work, "crate.glb"));
    expect(failure(await judged("crate.glb", {}, { maxFileBytes: 1000 }))).toMatchObject({ stage: "asset", code: "too_large" });
  });

  it("an invalid spec", async () => {
    copyFileSync(join(assets, "crate.glb"), join(work, "crate.glb"));
    const report = await judged("crate.glb", { triangles: { max: -1 }, colour: "red" });
    expect(failure(report)).toMatchObject({ stage: "spec", code: "invalid_spec" });
    expect(report.failure?.message).toContain("triangles.max");
    expect(report.failure?.message).toContain("colour");
  });

  it("a binary that is not Blender 5.2", async () => {
    copyFileSync(join(assets, "crate.glb"), join(work, "crate.glb"));
    const wrong = await judge({ specPath: writeSpec(work, "wrong-blender"), assetPath: join(work, "crate.glb"), outDir: freshDir("broken", "reports", "wrong-blender"), blender: process.execPath });
    expect(failure(wrong)).toMatchObject({ stage: "blender", code: "unsupported_blender" });
  });
});

describe("the blendworks judge command", { timeout: 120_000 }, () => {
  it("exits 0 when every rule passes and 1 when one fails", async () => {
    copyFileSync(join(assets, "crate.glb"), join(work, "crate.glb"));
    copyFileSync(join(assets, "wrong-size.glb"), join(work, "wrong-size.glb"));
    const spec = writeSpec(work, "command", { views: ["three-quarter"] });
    const passOut = freshDir("broken", "command-pass");
    expect(await main(["judge", spec, join(work, "crate.glb"), "--out", passOut])).toBe(0);
    expect(JSON.parse(readFileSync(join(passOut, "report.json"), "utf8")).blender).toMatch(/^5\.2\.\d+$/);
    expect(existsSync(join(passOut, "contact-sheet.png"))).toBe(true);
    expect(await main(["judge", spec, join(work, "wrong-size.glb"), "--out", freshDir("broken", "command-fail")])).toBe(1);
  });

  it("exits 2 on wrong usage", async () => {
    expect(await main(["judge", "only-a-spec.json"])).toBe(2);
    expect(await main(["judge", "a.json", "b.glb", "--timeout", "soon"])).toBe(2);
    expect(await main(["inspect", "a.json", "b.glb"])).toBe(2);
  });
});
