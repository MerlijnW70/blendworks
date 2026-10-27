import { describe, expect, it } from "vitest";
import { BRIDGE_MODULES, discoverTests, selectRelated } from "../../scripts/lib/fast-map.js";

const tests = discoverTests();

function pick(...changed: string[]) {
  return selectRelated(changed, tests);
}

describe("which tests check:fast runs", () => {
  it("always runs every unit test that needs no Blender, and nothing else for a docs change", () => {
    const selection = pick("README.md");
    expect(selection.vitest).toEqual([...tests.plain].sort());
    expect(selection.bridge).toEqual([]);
    expect(selection.vitest).toContain("test/judge/rules.test.ts");
    expect(selection.vitest).not.toContain("test/judge/preview.test.ts");
  });

  it("tells Blender tests from the others by their use of a Blender slot", () => {
    expect(tests.blender).toEqual(expect.arrayContaining(["test/judge/preview.test.ts", "test/session.test.ts", "test/mcp-e2e.test.ts", "test/library-textures.test.ts"]));
    expect(tests.plain).toEqual(expect.arrayContaining(["test/judge/rules.test.ts", "test/mcp-tools.test.ts", "test/tooling/blender-path.test.ts"]));
  });

  it("maps a judge source file to the judge test of the same name", () => {
    const selection = pick("src/judge/closeups.ts");
    expect(selection.vitest).toContain("test/judge/closeups.test.ts");
    expect(selection.vitest).not.toContain("test/judge/broken.test.ts");
  });

  it("maps a judge source file with no test of its own to every judge test", () => {
    const selection = pick("src/judge/run.ts");
    for (const name of ["broken", "closeups", "fixtures", "preview", "sandbox"]) expect(selection.vitest).toContain(`test/judge/${name}.test.ts`);
  });

  it("maps the packaging sources to the package tests and the bridge tests of the LOD core", () => {
    expect(pick("src/package/pipeline.ts").vitest).toEqual(expect.arrayContaining(["test/package/package.test.ts", "test/package/equivalence.test.ts"]));
    const core = pick("bridge/package/package_decimate.py");
    expect(core.vitest).toContain("test/package/package.test.ts");
    expect(core.bridge).toEqual(["test_lods.py", "test_package_math.py"]);
    expect(pick("bridge/blendworks_bridge/commands/lods.py").bridge).toEqual(["test_lods.py", "test_package_math.py"]);
  });

  it("maps a library source file to its library test, and an MCP file to its MCP test", () => {
    expect(pick("src/mcp/library/search.ts").vitest).toContain("test/library-search.test.ts");
    expect(pick("src/mcp/library/search.ts").vitest).not.toContain("test/library-textures.test.ts");
    expect(pick("src/mcp/connection.ts").vitest).toContain("test/mcp-connection.test.ts");
  });

  it("maps the session to its own test and the real-Blender MCP test", () => {
    const selection = pick("src/session.ts");
    expect(selection.vitest).toEqual(expect.arrayContaining(["test/session.test.ts", "test/mcp-e2e.test.ts"]));
  });

  it("maps a test helper to the tests that import it", () => {
    const selection = pick("test/judge/helpers.ts");
    expect(selection.vitest).toEqual(expect.arrayContaining(["test/judge/broken.test.ts", "test/judge/preview.test.ts", "test/judge/closeups.test.ts"]));
    expect(selection.vitest).not.toContain("test/session.test.ts");
  });

  it("maps bridge command modules to their bridge tests", () => {
    expect(pick("bridge/blendworks_bridge/commands/render.py").bridge).toEqual(["test_render.py"]);
    expect(pick("bridge/blendworks_bridge/commands/uv_pack.py").bridge).toEqual(["test_uv_texel.py"]);
    expect(pick("bridge/blendworks_bridge/baking.py").bridge).toEqual(["test_bake.py", "test_bake_failures.py", "test_textured_prop.py"]);
  });

  it("maps a bridge module with no table entry to the core bridge tests", () => {
    expect(pick("bridge/blendworks_bridge/handler.py").bridge).toEqual(["test_crate.py", "test_describe.py", "test_scene.py", "test_smoke.py"]);
  });

  it("runs the bridge test that changed, and the bridge tests that import a changed helper", () => {
    expect(pick("bridge/tests/test_images.py").bridge).toEqual(["test_images.py"]);
    expect(pick("bridge/tests/texture_helpers.py").bridge.length).toBeGreaterThan(0);
  });

  it("maps judge-side Python to the judge tests that run Blender", () => {
    expect(pick("bridge/judge/measure.py").vitest).toEqual(expect.arrayContaining(["test/judge/fixtures.test.ts", "test/judge/preview.test.ts"]));
  });

  it("maps the tooling to the tooling tests", () => {
    expect(pick("scripts/lib/slots.ts").vitest).toContain("test/tooling/concurrency.test.ts");
    expect(pick("package.json").vitest).toContain("test/tooling/bridge-runner.test.ts");
  });

  it("explains each choice", () => {
    expect(pick("src/judge/closeups.ts").reasons.join("\n")).toContain("src/judge/closeups.ts -> test/judge/closeups.test.ts");
  });
});

describe("the mapping table", () => {
  it("names only bridge test files that exist", () => {
    for (const [, names] of BRIDGE_MODULES) for (const name of names) expect(tests.bridge, name).toContain(name);
  });

  it("leaves no bridge test file unreachable from some bridge change", () => {
    const reachable = new Set(BRIDGE_MODULES.flatMap(([, names]) => names));
    const orphans = tests.bridge.filter((name) => !reachable.has(name) && pick(`bridge/tests/${name}`).bridge.join() !== name);
    expect(orphans).toEqual([]);
  });
});
