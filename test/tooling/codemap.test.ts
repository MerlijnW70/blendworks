import { existsSync, mkdirSync, mkdtempSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { buildMap, currentMap, descriptionProblems, MAX_MAP_BYTES, pythonModules, readDescriptions, repoTree, tooLarge, typeScriptSources, undocumentedModules, type Tree } from "../../scripts/lib/codemap.js";
import { repoRoot } from "../../scripts/lib/paths.js";

const made: string[] = [];

const ALPHA = '"""Alpha maths for the beta command."""\n\n\ndef scale_up(value):\n    return value * 2\n';
const BETA = '"""The beta command: doubles a number."""\n\nfrom ..registry import command\n\n\n@command(\n    "beta",\n    "Double a number.",\n)\ndef beta(ctx, args):\n    return args\n';
const FILES: Record<string, string> = {
  "bridge/blendworks_bridge/alpha.py": ALPHA,
  "bridge/blendworks_bridge/commands/beta.py": BETA,
  "bridge/tests/test_alpha.py": "run(globals())\n",
  "bridge/tests/test_beta.py": "run(globals())\n",
  "bridge/tests/test_alpha_more.py": "run(globals())\n",
  "src/x.ts": "export const X = 1;\n",
  "docs/codemap-descriptions.json": JSON.stringify({ "src/x.ts": "The constant X." }),
};

function miniTree(files: Record<string, string> = FILES): Tree {
  const root = mkdtempSync(join(tmpdir(), "blendworks-codemap-"));
  made.push(root);
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  return { root, tests: { plain: [], blender: [], bridge: ["test_alpha.py", "test_beta.py"] } };
}

afterEach(() => {
  for (const root of made.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("the code map lists what is in the tree", () => {
  it("names every bridge module, command and covering test, with its docstring line", () => {
    const map = buildMap(miniTree());
    expect(map).toContain("- `alpha`: Alpha maths for the beta command. | fn: scale_up | test: alpha");
    expect(map).toContain("- `beta`: The beta command: doubles a number. | cmd: beta | test: beta");
    expect(map).toContain("beta@beta");
    expect(map).toContain("- `x.ts`: The constant X.");
  });

  it("names every real module and command and the tests the existing test map gives it", () => {
    const map = buildMap();
    const modules = pythonModules();
    expect(modules.length).toBeGreaterThan(300);
    const commands = modules.flatMap((module) => module.commands.map((name) => `${name}@${module.name.replace(/\.py$/, "")}`));
    expect(commands.length).toBeGreaterThan(120);
    for (const entry of commands) expect(map, entry).toContain(entry);
    for (const module of modules) expect(map, module.path).toContain(`\`${module.name.replace(/\.py$/, "")}\`: ${module.doc}`);
    const abrade = modules.find((module) => module.path === "bridge/blendworks_bridge/abrasion.py");
    expect(abrade?.tests).toContain("test/rocks-example.test.ts");
    const erode = modules.find((module) => module.path === "bridge/blendworks_bridge/commands/erode.py");
    expect(erode?.commands).toEqual(["erode"]);
    expect(erode?.tests).toContain("test_erode.py");
  });

  it("points only at files that exist", () => {
    const text = buildMap();
    const paths = [...new Set([...text.matchAll(/`((?:[A-Za-z0-9_.-]+\/)+[A-Za-z0-9_.-]+\.(?:py|ts|mjs|md|json))`/g)].map((match) => match[1] ?? ""))];
    expect(paths.length).toBeGreaterThan(20);
    const missing = paths.filter((path) => !existsSync(join(repoRoot, path)));
    expect(missing).toEqual([]);
  });

  it("explains the layers and how to work", () => {
    const text = buildMap();
    for (const heading of ["## Layers", "## How to work", "**Run one test.**", "**Where things live.**", "**The shared Blender and the memory gate.**", "**Add a command.**", "**Add a limit.**", "**Add a test.**"]) expect(text, heading).toContain(heading);
    for (const phrase of ["npm run test:bridge --", "npx vitest run", "docs/examples", "BLENDWORKS_JOBS", "scripts/memory.json", "@command(", "limit(", "useBlenderSlot()"]) expect(text, phrase).toContain(phrase);
    for (const layer of ["MCP server", "Bridge", "Commands", "Judge", "Tests", "Scripts and benchmarks"]) expect(text, layer).toContain(`**${layer}`);
  });
});

describe("the code map is kept in sync", () => {
  it("is exactly what the generator writes for this tree", () => {
    expect(currentMap(), "run npx tsx scripts/codemap.mjs to regenerate docs/CODEMAP.md").toBe(buildMap());
  });

  it("goes stale when a module is added, removed or renamed", () => {
    const tree = miniTree();
    const written = buildMap(tree);
    writeFileSync(join(tree.root, "bridge/blendworks_bridge/gamma.py"), '"""Gamma."""\n');
    expect(buildMap(tree)).not.toBe(written);
    rmSync(join(tree.root, "bridge/blendworks_bridge/gamma.py"));
    expect(buildMap(tree)).toBe(written);
    rmSync(join(tree.root, "bridge/blendworks_bridge/alpha.py"));
    expect(buildMap(tree)).not.toBe(written);
    writeFileSync(join(tree.root, "bridge/blendworks_bridge/alpha.py"), ALPHA);
    renameSync(join(tree.root, "bridge/blendworks_bridge/alpha.py"), join(tree.root, "bridge/blendworks_bridge/alpha2.py"));
    expect(buildMap(tree)).not.toBe(written);
  });

  it("goes stale when a command is added, removed or renamed", () => {
    const tree = miniTree();
    const written = buildMap(tree);
    const path = join(tree.root, "bridge/blendworks_bridge/commands/beta.py");
    writeFileSync(path, BETA.replace('"beta",', '"beta_two",'));
    expect(buildMap(tree)).not.toBe(written);
    writeFileSync(path, BETA + '\n\n@command(\n    "delta",\n    "Another.",\n)\ndef delta(ctx, args):\n    return args\n');
    expect(buildMap(tree)).toContain("delta@beta");
    writeFileSync(path, BETA.replace('@command(\n    "beta",\n    "Double a number.",\n)\n', ""));
    expect(buildMap(tree)).not.toContain("beta@beta");
  });

  it("goes stale when a covering test is added or removed", () => {
    const tree = miniTree();
    const written = buildMap(tree);
    const widened = { root: tree.root, tests: { ...tree.tests, bridge: [...tree.tests.bridge, "test_alpha_more.py"] } };
    expect(buildMap(widened)).not.toBe(written);
  });

  it("goes stale when a TypeScript source is added and fails when its description is missing or stale", () => {
    const tree = miniTree();
    const written = buildMap(tree);
    writeFileSync(join(tree.root, "src/y.ts"), "export const Y = 2;\n");
    expect(buildMap(tree)).not.toBe(written);
    const sources = typeScriptSources(tree.root);
    expect(descriptionProblems(sources, readDescriptions(tree.root))).toEqual(["src/y.ts has no description in docs/codemap-descriptions.json"]);
    rmSync(join(tree.root, "src/x.ts"));
    rmSync(join(tree.root, "src/y.ts"));
    expect(descriptionProblems(typeScriptSources(tree.root), readDescriptions(tree.root))).toEqual(["docs/codemap-descriptions.json describes src/x.ts, which does not exist"]);
  });

  it("describes every real TypeScript source and nothing that is gone", () => {
    expect(descriptionProblems(typeScriptSources(), readDescriptions())).toEqual([]);
  });
});

describe("every bridge module has a docstring line", () => {
  it("finds the modules that have none", () => {
    const tree = miniTree({ ...FILES, "bridge/blendworks_bridge/bare.py": "import os\n", "bridge/blendworks_bridge/empty.py": '"""\nBody on the second line.\n"""\n' });
    expect(undocumentedModules(pythonModules(tree))).toEqual(["bridge/blendworks_bridge/bare.py", "bridge/blendworks_bridge/empty.py"]);
    expect(undocumentedModules(pythonModules(miniTree()))).toEqual([]);
  });

  it("holds for every module of the bridge, its commands, the judge, the package build and the add-on", () => {
    expect(undocumentedModules(pythonModules(repoTree()))).toEqual([]);
  });
});

describe("the code map stays compact", () => {
  it("is under its stated size", () => {
    const map = buildMap();
    expect(Buffer.byteLength(map)).toBeLessThanOrEqual(MAX_MAP_BYTES);
    expect(MAX_MAP_BYTES).toBeLessThanOrEqual(90_000);
    expect(tooLarge(map)).toBe(false);
  });

  it("notices a map past the limit", () => {
    expect(tooLarge("x".repeat(MAX_MAP_BYTES + 1))).toBe(true);
    expect(tooLarge("x".repeat(MAX_MAP_BYTES))).toBe(false);
  });
});
