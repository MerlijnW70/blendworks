import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { bridgeModuleTests, discoverTests, exampleTests, type TestSet } from "./fast-map.js";
import { repoRoot } from "./paths.js";

export const MAP_PATH = "docs/CODEMAP.md";
export const DESCRIPTIONS_PATH = "docs/codemap-descriptions.json";
export const AREAS_PATH = "docs/codemap-areas.json";
export const INDEX_TEMPLATE_PATH = "docs/codemap-index.md";
export const AREA_FOLDER = "docs/codemap";
export const MAX_INDEX_BYTES = 12_000;
export const MAX_AREA_BYTES = 20_000;

const PUBLIC_LIMIT = 2;
const TEST_LIMIT = 2;
const CORE_TESTS = ["test_smoke.py", "test_describe.py", "test_crate.py", "test_scene.py"];

export type Tree = { root: string; tests: TestSet };

export function repoTree(): Tree {
  return { root: repoRoot, tests: discoverTests() };
}

export type PythonModule = { path: string; group: string; name: string; doc: string | undefined; names: string[]; commands: string[]; tests: string[] };

export type TypeScriptSource = { path: string; group: string; description: string | undefined; exported: string[] };

const BRIDGE_GROUPS: { prefix: string; group: string }[] = [
  { prefix: "bridge/blendworks_bridge/commands/", group: "bridge/blendworks_bridge/commands" },
  { prefix: "bridge/blendworks_bridge/", group: "bridge/blendworks_bridge" },
  { prefix: "bridge/judge/", group: "bridge/judge" },
  { prefix: "bridge/package/", group: "bridge/package" },
  { prefix: "bridge/addon/", group: "bridge/addon" },
  { prefix: "bridge/", group: "bridge" },
];

function read(root: string, path: string): string {
  return readFileSync(join(root, path), "utf8").replace(/\r\n/g, "\n");
}

function walk(root: string, directory: string, extensions: string[], skip: (path: string) => boolean = () => false): string[] {
  const folder = join(root, directory);
  if (!existsSync(folder)) return [];
  const found: string[] = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = `${directory}/${entry.name}`;
    if (skip(path)) continue;
    if (entry.isDirectory()) found.push(...walk(root, path, extensions, skip));
    else if (extensions.some((extension) => entry.name.endsWith(extension))) found.push(path);
  }
  return found.sort();
}

export function pythonPaths(root: string = repoRoot): string[] {
  const skip = (path: string): boolean => /\/(tests|__pycache__|fixtures)$/.test(path);
  return walk(root, "bridge", [".py"], skip);
}

export function firstDocstringLine(source: string): string | undefined {
  const match = /^\s*r?"""([^\n]*)/.exec(source);
  if (match === null) return undefined;
  const line = (match[1] ?? "").replace(/"""\s*$/, "").trim();
  return line === "" ? undefined : line;
}

export function commandNames(source: string): string[] {
  return [...source.matchAll(/^@command\(\s*"([a-z0-9_]+)"/gm)].map((match) => match[1] ?? "");
}

export function publicNames(source: string): string[] {
  return [...source.matchAll(/^(?:def|class) ([A-Za-z][A-Za-z0-9_]*)/gm)].map((match) => match[1] ?? "");
}

function groupOf(path: string): string {
  return (BRIDGE_GROUPS.find((entry) => path.startsWith(entry.prefix)) ?? { group: "bridge" }).group;
}

function judgeOrPackageTests(path: string, vitest: string[]): string[] {
  if (path.startsWith("bridge/judge/")) return vitest.filter((test) => /^test\/judge\//.test(test)).length > 0 ? ["test/judge/"] : [];
  if (path.startsWith("bridge/package/")) return vitest.filter((test) => /^test\/package\//.test(test)).length > 0 ? ["test/package/"] : [];
  return [];
}

export function pythonModules(tree: Tree = repoTree()): PythonModule[] {
  const tests = tree.tests;
  const vitest = [...tests.plain, ...tests.blender];
  return pythonPaths(tree.root).map((path) => {
    const source = read(tree.root, path);
    const group = groupOf(path);
    const inBridgePackage = path.startsWith("bridge/blendworks_bridge/");
    const mapping = inBridgePackage && basename(path) !== "__init__.py" ? bridgeModuleTests(path, tests.bridge, join(tree.root, "bridge", "tests")) : { tests: [], how: "table" as const };
    const bridgeTests = mapping.how === "none" ? [] : mapping.tests;
    const examples = exampleTests(path, vitest);
    const own = path === "bridge/addon/server.py" || path === "bridge/addon/__init__.py" || path === "bridge/session.py" ? tests.bridge.filter((name) => name === "test_addon.py") : [];
    const found = [...bridgeTests, ...own, ...examples, ...judgeOrPackageTests(path, vitest)];
    const names = publicNames(source).filter((name) => !name.startsWith("_"));
    return { path, group, name: basename(path), doc: firstDocstringLine(source), names, commands: commandNames(source), tests: found };
  });
}

export function undocumentedModules(modules: PythonModule[]): string[] {
  return modules.filter((module) => module.doc === undefined).map((module) => module.path);
}

export function typeScriptPaths(root: string = repoRoot): string[] {
  const code = [".ts", ".mjs", ".js"];
  const keep = (path: string): boolean => !/\/(node_modules|dist|results)$/.test(path);
  return ["src", "scripts", "bench"].flatMap((folder) => walk(root, folder, code, (path) => !keep(path))).sort();
}

export function readDescriptions(root: string = repoRoot): Record<string, string> {
  return JSON.parse(read(root, DESCRIPTIONS_PATH)) as Record<string, string>;
}

export function typeScriptSources(root: string = repoRoot, descriptions: Record<string, string> = readDescriptions(root)): TypeScriptSource[] {
  return typeScriptPaths(root).map((path) => {
    const exported = [...read(root, path).matchAll(/^export (?:async )?(?:function|const|class|type|interface) ([A-Za-z0-9_]+)/gm)].map((match) => match[1] ?? "");
    const parts = path.split("/");
    const group = parts.length > 2 ? parts.slice(0, -1).join("/") : parts[0] ?? "";
    return { path, group, description: descriptions[path], exported };
  });
}

export function descriptionProblems(sources: TypeScriptSource[], descriptions: Record<string, string>): string[] {
  const problems = sources.filter((source) => source.description === undefined || source.description.trim() === "").map((source) => `${source.path} has no description in ${DESCRIPTIONS_PATH}`);
  const known = new Set(sources.map((source) => source.path));
  for (const path of Object.keys(descriptions)) if (!known.has(path)) problems.push(`${DESCRIPTIONS_PATH} describes ${path}, which does not exist`);
  return problems;
}

function testLabel(name: string): string {
  return name.replace(/^test_/, "").replace(/\.py$/, "");
}

function moduleLine(module: PythonModule): string {
  const parts = [`- \`${module.name.replace(/\.py$/, "")}\`: ${module.doc ?? "(no docstring)"}`];
  const helpers = module.names.filter((name) => !module.commands.includes(name));
  if (helpers.length > 0) parts.push(`fn: ${helpers.slice(0, PUBLIC_LIMIT).join(" ")}${helpers.length > PUBLIC_LIMIT ? " +" : ""}`);
  if (module.commands.length > 0) parts.push(`cmd: ${module.commands.join(" ")}`);
  if (module.tests.length > 0) {
    const shown = module.tests.slice(0, TEST_LIMIT).map((test) => (test.endsWith(".py") ? testLabel(test) : test.replace(/^test\//, "").replace(/\.test\.ts$/, "")));
    parts.push(`test: ${shown.join(" ")}${module.tests.length > TEST_LIMIT ? ` +${module.tests.length - TEST_LIMIT}` : ""}`);
  }
  return parts.join(" | ");
}

function groupBy<T>(items: T[], key: (item: T) => string): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) groups.set(key(item), [...(groups.get(key(item)) ?? []), item]);
  return [...groups.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
}


export type Area = { id: string; title: string; blurb: string; match: RegExp[] };

export function readAreas(root: string = repoRoot): Area[] {
  const parsed = JSON.parse(read(root, AREAS_PATH)) as { areas: { id: string; title: string; blurb: string; match: string[] }[] };
  return parsed.areas.map((area) => ({ ...area, match: area.match.map((pattern) => new RegExp(pattern)) }));
}

export function areaKey(path: string): string {
  const python = /^bridge\/blendworks_bridge\/(?:commands\/)?([^/]+)\.py$/.exec(path);
  return python === null ? path : `py:${python[1] ?? ""}`;
}

export function areaOf(path: string, areas: Area[]): string | undefined {
  const key = areaKey(path);
  return areas.find((area) => area.match.some((pattern) => pattern.test(key)))?.id;
}

export function filesWithoutArea(tree: Tree, areas: Area[] = readAreas(tree.root)): string[] {
  const paths = [...pythonPaths(tree.root), ...typeScriptPaths(tree.root)];
  return paths.filter((path) => areaOf(path, areas) === undefined);
}

function bridgeSection(modules: PythonModule[]): string[] {
  const out: string[] = [];
  for (const [group, members] of groupBy(modules, (module) => module.group)) out.push(`### ${group}/ (${members.length})`, "", ...members.map(moduleLine), "");
  return out;
}

function sourceLine(source: TypeScriptSource): string {
  const name = basename(source.path);
  return `- \`${name}\`: ${source.description ?? `(exports ${source.exported.slice(0, 3).join(", ")})`}`;
}

function typeScriptSection(sources: TypeScriptSource[]): string[] {
  const out: string[] = [];
  for (const [group, members] of groupBy(sources, (source) => source.group)) out.push(`### ${group}/ (${members.length})`, "", ...members.map(sourceLine), "");
  return out;
}

function testsSection(tree: Tree): string[] {
  const tests = tree.tests;
  const stems = (names: string[], prefix: string): string => names.map((name) => name.replace(prefix, "").replace(/\.test\.ts$/, "").replace(/^test_/, "").replace(/\.py$/, "")).join(" ");
  const bridgeFolder = join(tree.root, "bridge", "tests");
  const helpers = existsSync(bridgeFolder) ? readdirSync(bridgeFolder).filter((name) => name.endsWith(".py") && !name.startsWith("test_")).sort() : [];
  const out = ["### Tests", ""];
  out.push(`- \`test/\` (vitest, ${tests.plain.length} files without Blender): ${stems(tests.plain, "test/")}`, "");
  out.push(`- \`test/\` (vitest, ${tests.blender.length} files that start Blender through \`useBlenderSlot()\`): ${stems(tests.blender, "test/")}`, "");
  out.push(`- \`bridge/tests/test_<name>.py\` (${tests.bridge.length} files, run inside Blender): ${stems(tests.bridge, "")}`, "");
  out.push(`- \`bridge/tests/\` helpers, not tests: ${helpers.join(" ")}`, "");
  return out;
}

const LINE_NOTE = "One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (" + CORE_TESTS.map(testLabel).join(", ") + ").";

function areaMap(area: Area, modules: PythonModule[], sources: TypeScriptSource[], tree: Tree, areas: Area[]): string {
  const own = modules.filter((module) => areaOf(module.path, areas) === area.id);
  const scripts = sources.filter((source) => areaOf(source.path, areas) === area.id);
  const out = [`# Code map: ${area.title}`, "", `${area.blurb} Part of [the code map index](../CODEMAP.md).`, "", LINE_NOTE, ""];
  out.push(...bridgeSection(own), ...typeScriptSection(scripts));
  if (area.id === "tooling") out.push(...testsSection(tree));
  return `${out.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}

function sortedPairs(pairs: (readonly [string, string])[]): (readonly [string, string])[] {
  return pairs.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
}

export function buildMaps(tree: Tree = repoTree()): Record<string, string> {
  const areas = readAreas(tree.root);
  const orphans = filesWithoutArea(tree, areas);
  if (orphans.length > 0) throw new Error(`no area in ${AREAS_PATH} takes: ${orphans.join(", ")}`);
  const modules = pythonModules(tree);
  const sources = typeScriptSources(tree.root);
  const maps: Record<string, string> = {};
  const lines: string[] = [];
  for (const area of areas) {
    const members = modules.filter((module) => areaOf(module.path, areas) === area.id).length;
    const files = sources.filter((source) => areaOf(source.path, areas) === area.id).length;
    if (members + files === 0) continue;
    maps[`${AREA_FOLDER}/${area.id}.md`] = areaMap(area, modules, sources, tree, areas);
    lines.push(`- [${area.title}](codemap/${area.id}.md): ${area.blurb}`);
  }
  const commands = sortedPairs(modules.flatMap((module) => module.commands.map((name) => [name, areaOf(module.path, areas) ?? ""] as const)));
  const index = read(tree.root, INDEX_TEMPLATE_PATH).replace("{{AREAS}}", lines.join("\n")).replace("{{COMMANDS}}", `${commands.length} commands: ${commands.map(([name, id]) => `${name}@${id}`).join(" ")}`);
  maps[MAP_PATH] = `${index.trimEnd()}\n`;
  return maps;
}

export function currentMaps(root: string = repoRoot): Record<string, string> {
  const found: Record<string, string> = {};
  if (existsSync(join(root, MAP_PATH))) found[MAP_PATH] = read(root, MAP_PATH);
  const folder = join(root, AREA_FOLDER);
  if (existsSync(folder)) for (const name of readdirSync(folder).filter((entry) => entry.endsWith(".md")).sort()) found[`${AREA_FOLDER}/${name}`] = read(root, `${AREA_FOLDER}/${name}`);
  return found;
}

export function staleMaps(built: Record<string, string>, current: Record<string, string>): string[] {
  const paths = [...new Set([...Object.keys(built), ...Object.keys(current)])].sort();
  return paths.filter((path) => built[path] !== current[path]);
}

export function sizeProblems(maps: Record<string, string>): string[] {
  const problems: string[] = [];
  for (const [path, text] of Object.entries(maps)) {
    const bytes = Buffer.byteLength(text);
    if (path === MAP_PATH && bytes > MAX_INDEX_BYTES) problems.push(`${path} is ${bytes} bytes, over ${MAX_INDEX_BYTES}: shorten the index template ${INDEX_TEMPLATE_PATH}`);
    if (path !== MAP_PATH && bytes > MAX_AREA_BYTES) problems.push(`${path} is ${bytes} bytes, over ${MAX_AREA_BYTES}: split this area in ${AREAS_PATH} into two areas; do not trim descriptions`);
  }
  return problems;
}
