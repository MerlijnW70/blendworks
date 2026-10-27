import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { JUDGE_RENDER, renderProfile, TEST_RENDER, TEST_RENDER_VARIABLE } from "../../src/judge/render-profile.js";
import { RENDER_RESOLUTION, RENDER_SAMPLES } from "../../src/judge/render-stage.js";
import { judge } from "../../src/judge/run.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";

useBlenderSlot();

const saved = process.env[TEST_RENDER_VARIABLE];
let assets = "";
let specs = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtures("render-profile"));
  specs = freshDir("render-profile", "specs");
}));

afterEach(() => {
  if (saved === undefined) delete process.env[TEST_RENDER_VARIABLE];
  else process.env[TEST_RENDER_VARIABLE] = saved;
});

function pngSize(path: string): [number, number] {
  const bytes = readFileSync(path);
  return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
}

function files(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

async function frontView(name: string): Promise<[number, number]> {
  const spec = writeSpec(specs, name, { views: ["front"] });
  const report = await judge({ specPath: spec, assetPath: join(assets, "crate.glb"), outDir: freshDir("render-profile", "reports", name), device: "cpu" });
  expect(report.renders?.status).toBe("rendered");
  return pngSize(report.renders!.views[0]!.path);
}

describe("the test render profile", () => {
  it("is off unless the variable asks for it, and the judge's defaults stay 512 px and 24 samples", () => {
    expect(renderProfile({})).toEqual({ name: "judge", resolution: 512, samples: 24 });
    expect(renderProfile({ [TEST_RENDER_VARIABLE]: "" })).toBe(JUDGE_RENDER);
    expect([RENDER_RESOLUTION, RENDER_SAMPLES]).toEqual([512, 24]);
    expect(renderProfile({ [TEST_RENDER_VARIABLE]: "test" })).toEqual({ name: "test", resolution: 128, samples: 4 });
    expect(() => renderProfile({ [TEST_RENDER_VARIABLE]: "fast" })).toThrow(/for the test suite only/);
    expect(TEST_RENDER.resolution).toBeLessThan(JUDGE_RENDER.resolution);
  });

  it("is read in one place in the production code, and set only by the test configuration", () => {
    const readers = [...files("src"), ...files("bridge"), ...files("scripts")]
      .filter((path) => /\.(ts|py|mjs|sh)$/.test(path))
      .filter((path) => readFileSync(path, "utf8").includes(TEST_RENDER_VARIABLE))
      .map((path) => relative(".", path).split(sep).join("/"));
    expect(readers).toEqual(["src/judge/render-profile.ts"]);
    expect(readFileSync("vitest.config.ts", "utf8")).toContain(`${TEST_RENDER_VARIABLE}: "test"`);
  });
});

describe("renders with and without the test render profile", workBudget(120_000), () => {
  it("renders the judge's 512 px views when the variable is unset, so the profile cannot leak into production", async () => {
    delete process.env[TEST_RENDER_VARIABLE];
    expect(await frontView("production")).toEqual([512, 512]);
  });

  it("renders 128 px views under the test profile", async () => {
    process.env[TEST_RENDER_VARIABLE] = "test";
    expect(await frontView("profile")).toEqual([128, 128]);
  });
});
