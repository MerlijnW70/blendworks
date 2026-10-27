import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { repoRoot } from "../../scripts/lib/paths.js";

const ASSET_EXTENSIONS = /\.(glb|gltf|blend|blend1|fbx|obj|mtl|bin|abc|usd|usdz|ply|stl)$/i;
const ONE_PROCESS_TESTS = ["test/judge/equivalence.test.ts", "test/judge/stage-isolation.test.ts", "test/judge/stage-crash.test.ts", "test/judge/one-process.test.ts"];

function tracked(): string[] {
  return execFileSync("git", ["ls-files"], { cwd: repoRoot, encoding: "utf8" }).split("\n").filter(Boolean);
}

describe("judge fixtures", () => {
  it("are never committed as binaries: no tracked file is a 3D asset", () => {
    expect(tracked().filter((path) => ASSET_EXTENSIONS.test(path))).toEqual([]);
  });

  it("come from the fixture scripts in the one-process judge tests", () => {
    for (const file of ONE_PROCESS_TESTS) expect(readFileSync(`${repoRoot}/${file}`, "utf8")).toMatch(/makeFixtures?(Set)?\(|inject\("fixtureSets"\)/);
  });
});
