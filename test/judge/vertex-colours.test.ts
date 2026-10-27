import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";

useBlenderSlot();

let assets = "";
let specs = "";

beforeAll(() => {
  ({ assets } = makeFixtureSet("colour_fixtures", "vertex-colours"));
  specs = freshDir("vertex-colours", "specs");
}, 180_000);

async function judged(asset: string, vertexColors: Record<string, unknown>, label: string): Promise<Report> {
  const spec = join(specs, `${asset}-${label}.spec.json`);
  writeFileSync(spec, JSON.stringify({ format: asset.split(".").pop(), views: ["front"], vertexColors }));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("vertex-colours", "reports", `${asset}-${label}`), preview: true });
}

function verdicts(report: Report): [string, boolean][] {
  return report.rules.map((rule) => [rule.rule, rule.pass]);
}

describe("vertex colours", { timeout: 180_000 }, () => {
  it("two painted cubes: a corner colour on both meshes, in bytes as glTF carries it", async () => {
    const report = await judged("painted.glb", { required: true, domain: "corner" }, "corner");
    expect(verdicts(report)).toEqual([
      ["format", true],
      ["vertexColors.required", true],
      ["vertexColors.domain", true],
    ]);
    expect(report.measurements!.vertexColors).toEqual({
      meshes: 2,
      withColours: 2,
      attributes: 2,
      domains: { point: 0, corner: 2 },
      types: { byte: 2, float: 0 },
      without: [],
      items: [
        { mesh: "Painted", attributes: [{ name: "Color", domain: "corner", type: "byte" }] },
        { mesh: "Trim", attributes: [{ name: "Color", domain: "corner", type: "byte" }] },
      ],
    });
  });

  it("one cube left unpainted fails required, and passes once the rule is removed", async () => {
    const report = await judged("painted-partly.glb", { required: true }, "required");
    expect(verdicts(report)).toEqual([
      ["format", true],
      ["vertexColors.required", false],
    ]);
    expect(report.rules[1]!.measured).toEqual({ meshes: 2, withColours: 1, without: ["Trim"] });
    expect((await judged("painted-partly.glb", {}, "free")).passed).toBe(true);
  });

  it("colours stored per point in a .blend fail a corner domain and pass a point domain", async () => {
    const corner = await judged("painted-points.blend", { required: true, domain: "corner" }, "corner");
    expect(verdicts(corner)).toEqual([
      ["format", true],
      ["vertexColors.required", true],
      ["vertexColors.domain", false],
    ]);
    expect(corner.measurements!.vertexColors).toMatchObject({ domains: { point: 2, corner: 0 }, types: { byte: 0, float: 2 } });
    expect((await judged("painted-points.blend", { domain: "point" }, "point")).passed).toBe(true);
  });
});
