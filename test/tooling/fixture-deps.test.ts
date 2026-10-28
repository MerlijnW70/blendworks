import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { declarationAdvice, declaredDependencies, dependencyFiles, importedProjectFiles, uncoveredImports } from "../../scripts/lib/fixture-deps.js";
import { fixtureKey, fixtureSets } from "../../scripts/lib/fixtures.js";
import { repoRoot } from "../../scripts/lib/paths.js";
import { scratch } from "./probes.js";

function project(): { base: string; write(path: string, text: string): string } {
  const base = scratch("fixture-deps");
  return {
    base,
    write(path, text) {
      const file = join(base, path);
      mkdirSync(join(file, ".."), { recursive: true });
      writeFileSync(file, text);
      return file;
    },
  };
}

describe("what each fixture script depends on", () => {
  it("is declared by every real fixture script and covers every bridge or judge module it imports", () => {
    expect(fixtureSets().length).toBeGreaterThan(5);
    for (const set of fixtureSets()) {
      expect(readFileSync(set.script, "utf8"), set.name).toMatch(/^FIXTURE_DEPS = \(/m);
      expect(declarationAdvice(set.script), set.name).toEqual([]);
    }
  });

  it("is exactly the bridge tree for the script that imports it, one judge module for the script that imports that, and nothing for the rest", () => {
    const files = (name: string) => dependencyFiles(declaredDependencies(join(repoRoot, "test", "judge", `${name}.py`)));
    expect(files("visual_fixtures")).toEqual(["bridge/judge/judge_font.py"]);
    expect(files("rocks_fixtures").every((file) => file.startsWith("bridge/blendworks_bridge/"))).toBe(true);
    expect(files("rocks_fixtures")).toContain("bridge/blendworks_bridge/__init__.py");
    for (const name of ["fixtures", "colour_fixtures", "integrity_fixtures", "natural_fixtures", "package_fixtures", "rig_fixtures", "texture_fixtures"]) expect(files(name), name).toEqual([]);
  });

  it("is found by tracing the imports of a script and of the judge modules it imports", () => {
    const { base, write } = project();
    write("bridge/judge/judge_a.py", "import judge_b\n");
    write("bridge/judge/judge_b.py", "x = 1\n");
    write("bridge/blendworks_bridge/__init__.py", "x = 1\n");
    const script = write("test/judge/one_fixtures.py", "import os\nimport bpy\nfrom judge_a import thing\nfrom blendworks_bridge.commands import abrade\n");
    expect(importedProjectFiles(script, base)).toEqual(["bridge/blendworks_bridge", "bridge/judge/judge_a.py", "bridge/judge/judge_b.py"]);
  });

  it("is reported when a script imports a bridge or judge module that it does not declare", () => {
    const { base, write } = project();
    write("bridge/judge/judge_font.py", "x = 1\n");
    write("bridge/judge/judge_other.py", "x = 1\n");
    write("bridge/blendworks_bridge/__init__.py", "x = 1\n");
    const forgetful = write("test/judge/a_fixtures.py", 'FIXTURE_DEPS = ()\nfrom judge_font import draw\nfrom blendworks_bridge import Handler\n');
    expect(uncoveredImports(forgetful, base)).toEqual(["bridge/blendworks_bridge", "bridge/judge/judge_font.py"]);
    expect(declarationAdvice(forgetful, base)).toEqual([`test/judge/a_fixtures.py imports bridge/blendworks_bridge, bridge/judge/judge_font.py but its cache key does not cover it: make its first line  FIXTURE_DEPS = ("bridge/blendworks_bridge", "bridge/judge/judge_font.py")`]);
    const partial = write("test/judge/b_fixtures.py", 'FIXTURE_DEPS = ("bridge/judge/judge_other.py",)\nfrom judge_font import draw\n');
    expect(uncoveredImports(partial, base)).toEqual(["bridge/judge/judge_font.py"]);
    const complete = write("test/judge/c_fixtures.py", 'FIXTURE_DEPS = ("bridge/judge/judge_font.py", "bridge/blendworks_bridge")\nfrom judge_font import draw\nfrom blendworks_bridge import Handler\n');
    expect(uncoveredImports(complete, base)).toEqual([]);
  });
});

describe("the fixture cache key", () => {
  it("hashes the declared files and nothing else: a bridge edit leaves the key of a script that does not import the bridge alone", () => {
    const { base, write } = project();
    write("bridge/blendworks_bridge/commands/abrade.py", "x = 1\n");
    const judge = write("bridge/judge/judge_font.py", "x = 1\n");
    const plain = write("test/judge/plain_fixtures.py", "FIXTURE_DEPS = ()\nprint(1)\n");
    const bridged = write("test/judge/bridged_fixtures.py", 'FIXTURE_DEPS = ("bridge/blendworks_bridge",)\nprint(1)\n');
    const fonted = write("test/judge/fonted_fixtures.py", 'FIXTURE_DEPS = ("bridge/judge/judge_font.py",)\nprint(1)\n');
    const before = [plain, bridged, fonted].map((script) => fixtureKey(script, "5.2", base));
    write("bridge/blendworks_bridge/commands/abrade.py", "x = 2\n");
    const afterBridge = [plain, bridged, fonted].map((script) => fixtureKey(script, "5.2", base));
    expect(afterBridge[0]).toBe(before[0]);
    expect(afterBridge[1]).not.toBe(before[1]);
    expect(afterBridge[2]).toBe(before[2]);
    writeFileSync(judge, "x = 2\n");
    const afterJudge = [plain, bridged, fonted].map((script) => fixtureKey(script, "5.2", base));
    expect(afterJudge[0]).toBe(afterBridge[0]);
    expect(afterJudge[1]).toBe(afterBridge[1]);
    expect(afterJudge[2]).not.toBe(afterBridge[2]);
    write("bridge/judge/judge_other.py", "x = 1\n");
    expect([plain, bridged, fonted].map((script) => fixtureKey(script, "5.2", base))).toEqual(afterJudge);
  });
});
