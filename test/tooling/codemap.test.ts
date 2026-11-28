import { existsSync, mkdirSync, mkdtempSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { AREA_FOLDER, buildMaps, currentMaps, descriptionProblems, filesWithoutArea, MAP_PATH, MAX_AREA_BYTES, MAX_INDEX_BYTES, pythonModules, readAreas, readDescriptions, repoTree, sizeProblems, staleMaps, typeScriptSources, undocumentedModules, type Tree } from "../../scripts/lib/codemap.js";
import { repoRoot } from "../../scripts/lib/paths.js";

const made: string[] = [];

const ALPHA = '"""Alpha maths for the beta command."""\n\n\ndef scale_up(value):\n    return value * 2\n';
const BETA = '"""The beta command: doubles a number."""\n\nfrom ..registry import command\n\n\n@command(\n    "beta",\n    "Double a number.",\n)\ndef beta(ctx, args):\n    return args\n';
const AREAS = JSON.stringify({ areas: [{ id: "maths", title: "Maths", blurb: "Alpha and beta.", match: ["^py:(alpha|beta|new_.*)$"] }, { id: "sources", title: "Sources", blurb: "TypeScript.", match: ["^src/"] }] });
const TEMPLATE = "# Code map\n\n## Areas\n\n{{AREAS}}\n\n## Command lookup\n\n{{COMMANDS}}\n";
const FILES: Record<string, string> = {
  "bridge/blendworks_bridge/alpha.py": ALPHA,
  "bridge/blendworks_bridge/commands/beta.py": BETA,
  "bridge/tests/test_alpha.py": "run(globals())\n",
  "bridge/tests/test_beta.py": "run(globals())\n",
  "bridge/tests/test_alpha_more.py": "run(globals())\n",
  "src/x.ts": "export const X = 1;\n",
  "docs/codemap-descriptions.json": JSON.stringify({ "src/x.ts": "The constant X." }),
  "docs/codemap-areas.json": AREAS,
  "docs/codemap-index.md": TEMPLATE,
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

const AREA_MAP = `${AREA_FOLDER}/maths.md`;

afterEach(() => {
  for (const root of made.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("the code map is an index plus one map per area", () => {
  it("lists each area with a link in the index and a command lookup, and puts each module in its area map", () => {
    const maps = buildMaps(miniTree());
    expect(Object.keys(maps).sort()).toEqual([MAP_PATH, AREA_MAP, `${AREA_FOLDER}/sources.md`].sort());
    expect(maps[MAP_PATH]).toContain("- [Maths](codemap/maths.md): Alpha and beta.");
    expect(maps[MAP_PATH]).toContain("1 commands: beta@maths");
    expect(maps[AREA_MAP]).toContain("- `alpha`: Alpha maths for the beta command. | fn: scale_up | test: alpha");
    expect(maps[AREA_MAP]).toContain("- `beta`: The beta command: doubles a number. | cmd: beta | test: beta");
    expect(maps[AREA_MAP]).not.toContain("x.ts");
    expect(maps[`${AREA_FOLDER}/sources.md`]).toContain("- `x.ts`: The constant X.");
  });

  it("keeps the layer overview and the how-to-work section in the real index", () => {
    const text = buildMaps()[MAP_PATH] ?? "";
    for (const heading of ["## Layers", "## How to work", "## Areas", "## Command lookup", "**Run one test.**", "**Where things live.**", "**The shared Blender and the memory gate.**", "**Add a command.**", "**Add a limit.**", "**Add a test.**"]) expect(text, heading).toContain(heading);
    for (const phrase of ["npm run test:bridge --", "npx vitest run", "docs/examples", "BLENDWORKS_JOBS", "scripts/memory.json", "@command(", "limit(", "useBlenderSlot()"]) expect(text, phrase).toContain(phrase);
    for (const layer of ["MCP server", "Bridge", "Commands", "Judge", "Tests", "Scripts and benchmarks"]) expect(text, layer).toContain(`**${layer}`);
  });

  it("links every real area and looks every real command up in a map that exists", () => {
    const maps = buildMaps();
    const index = maps[MAP_PATH] ?? "";
    const areaFiles = Object.keys(maps).filter((path) => path !== MAP_PATH);
    expect(areaFiles.length).toBeGreaterThanOrEqual(8);
    for (const path of areaFiles) expect(index, path).toContain(`(${path.replace(/^docs\//, "")})`);
    const areas = readAreas();
    const ids = new Set(areas.map((area) => area.id));
    const lookups = [...index.matchAll(/ ([a-z0-9_]+)@([a-z-]+)/g)];
    expect(lookups.length).toBeGreaterThan(120);
    for (const [, , id] of lookups) expect(ids.has(id ?? ""), id).toBe(true);
    for (const module of pythonModules()) for (const command of module.commands) expect(index, command).toContain(` ${command}@`);
  });

  it("names every real module with its docstring and tests in some area map", () => {
    const maps = buildMaps();
    const all = Object.values(maps).join("\n");
    const modules = pythonModules();
    expect(modules.length).toBeGreaterThan(300);
    for (const module of modules) expect(all, module.path).toContain(`\`${module.name.replace(/\.py$/, "")}\`: ${module.doc}`);
    const erode = modules.find((module) => module.path === "bridge/blendworks_bridge/commands/erode.py");
    expect(erode?.commands).toEqual(["erode"]);
    expect(erode?.tests).toContain("test_erode.py");
  });

  it("points only at files that exist", () => {
    const text = Object.values(buildMaps()).join("\n");
    const paths = [...new Set([...text.matchAll(/`((?:[A-Za-z0-9_.-]+\/)+[A-Za-z0-9_.-]+\.(?:py|ts|mjs|md|json))`/g)].map((match) => match[1] ?? ""))];
    expect(paths.length).toBeGreaterThan(20);
    expect(paths.filter((path) => !existsSync(join(repoRoot, path)))).toEqual([]);
  });
});

describe("areas are derived by rule", () => {
  it("lands a new module in its area without any edit to the maps", () => {
    const tree = miniTree();
    writeFileSync(join(tree.root, "bridge/blendworks_bridge/new_thing.py"), '"""A new thing."""\n');
    const maps = buildMaps(tree);
    expect(maps[AREA_MAP]).toContain("- `new_thing`: A new thing.");
    expect(maps[`${AREA_FOLDER}/sources.md`]).not.toContain("new_thing");
  });

  it("names the module that has no area and refuses to build", () => {
    const tree = miniTree();
    writeFileSync(join(tree.root, "bridge/blendworks_bridge/orphan.py"), '"""Nobody takes this."""\n');
    expect(filesWithoutArea(tree)).toEqual(["bridge/blendworks_bridge/orphan.py"]);
    expect(() => buildMaps(tree)).toThrow(/orphan\.py/);
  });

  it("gives every file of the real tree an area", () => {
    expect(filesWithoutArea(repoTree())).toEqual([]);
  });
});

describe("every map stays under its limit", () => {
  it("keeps the real index and every real area map within their stated sizes", () => {
    const maps = buildMaps();
    expect(sizeProblems(maps)).toEqual([]);
    expect(MAX_INDEX_BYTES).toBeLessThanOrEqual(12_000);
    expect(MAX_AREA_BYTES).toBeLessThanOrEqual(20_000);
  });

  it("tells a worker to split an area that grows past its limit, not to trim descriptions", () => {
    const files = { ...FILES };
    for (let index = 0; index < 300; index += 1) files[`bridge/blendworks_bridge/new_${String(index).padStart(3, "0")}.py`] = `"""A module number ${index} with a docstring line that is long enough to count."""\n\n\ndef function_${index}():\n    return ${index}\n`;
    const problems = sizeProblems(buildMaps(miniTree(files)));
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain(AREA_MAP);
    expect(problems[0]).toContain("split this area");
    expect(problems[0]).toContain("do not trim descriptions");
  });

  it("holds the index to its own, smaller limit", () => {
    const problems = sizeProblems({ [MAP_PATH]: "x".repeat(MAX_INDEX_BYTES + 1), [AREA_MAP]: "x".repeat(MAX_INDEX_BYTES + 1) });
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain(MAP_PATH);
    expect(sizeProblems({ [MAP_PATH]: "x".repeat(MAX_INDEX_BYTES), [AREA_MAP]: "x".repeat(MAX_AREA_BYTES) })).toEqual([]);
  });
});

describe("the maps are kept in sync", () => {
  it("are exactly what the generator writes for this tree", () => {
    expect(staleMaps(buildMaps(), currentMaps()), "run npx tsx scripts/codemap.mjs to regenerate docs/CODEMAP.md and docs/codemap/").toEqual([]);
  });

  it("go stale when a module is added, removed or renamed", () => {
    const tree = miniTree();
    const written = buildMaps(tree);
    writeFileSync(join(tree.root, "bridge/blendworks_bridge/new_gamma.py"), '"""Gamma."""\n');
    expect(staleMaps(buildMaps(tree), written)).toEqual([AREA_MAP]);
    rmSync(join(tree.root, "bridge/blendworks_bridge/new_gamma.py"));
    expect(staleMaps(buildMaps(tree), written)).toEqual([]);
    rmSync(join(tree.root, "bridge/blendworks_bridge/alpha.py"));
    expect(staleMaps(buildMaps(tree), written)).toEqual([AREA_MAP]);
    writeFileSync(join(tree.root, "bridge/blendworks_bridge/alpha.py"), ALPHA);
    renameSync(join(tree.root, "bridge/blendworks_bridge/alpha.py"), join(tree.root, "bridge/blendworks_bridge/new_alpha.py"));
    expect(staleMaps(buildMaps(tree), written)).toEqual([AREA_MAP]);
  });

  it("go stale, index included, when a command is added, removed or renamed", () => {
    const tree = miniTree();
    const written = buildMaps(tree);
    const path = join(tree.root, "bridge/blendworks_bridge/commands/beta.py");
    writeFileSync(path, BETA.replace('"beta",', '"beta_two",'));
    expect(staleMaps(buildMaps(tree), written)).toEqual([MAP_PATH, AREA_MAP]);
    writeFileSync(path, BETA.replace('@command(\n    "beta",\n    "Double a number.",\n)\n', ""));
    expect(buildMaps(tree)[MAP_PATH]).not.toContain("beta@maths");
  });

  it("go stale when a covering test is added", () => {
    const tree = miniTree();
    const written = buildMaps(tree);
    const widened = { root: tree.root, tests: { ...tree.tests, bridge: [...tree.tests.bridge, "test_alpha_more.py"] } };
    expect(staleMaps(buildMaps(widened), written)).toEqual([AREA_MAP]);
  });

  it("go stale when an area map is missing or left over", () => {
    const tree = miniTree();
    const written = buildMaps(tree);
    const { [AREA_MAP]: dropped, ...rest } = written;
    expect(dropped).toBeDefined();
    expect(staleMaps(written, rest)).toEqual([AREA_MAP]);
    expect(staleMaps(rest, written)).toEqual([AREA_MAP]);
  });

  it("go stale when a TypeScript source is added, and fail when its description is missing or stale", () => {
    const tree = miniTree();
    const written = buildMaps(tree);
    writeFileSync(join(tree.root, "src/y.ts"), "export const Y = 2;\n");
    expect(staleMaps(buildMaps(tree), written)).toEqual([`${AREA_FOLDER}/sources.md`]);
    const sources = typeScriptSources(tree.root);
    expect(descriptionProblems(sources, readDescriptions(tree.root))).toEqual(["src/y.ts has no description in docs/codemap-descriptions.json"]);
    rmSync(join(tree.root, "src/x.ts"));
    rmSync(join(tree.root, "src/y.ts"));
    expect(descriptionProblems(typeScriptSources(tree.root), readDescriptions(tree.root))).toEqual(["docs/codemap-descriptions.json describes src/x.ts, which does not exist"]);
  });

  it("describe every real TypeScript source and nothing that is gone", () => {
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
