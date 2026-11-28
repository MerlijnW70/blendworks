import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { bridgeModuleTests, discoverTests, exampleTests, type TestSet } from "./fast-map.js";
import { repoRoot } from "./paths.js";

export const MAP_PATH = "docs/CODEMAP.md";
export const DESCRIPTIONS_PATH = "docs/codemap-descriptions.json";
export const MAX_MAP_BYTES = 85_000;

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

function bridgeSection(modules: PythonModule[]): string[] {
  const out = ["## Bridge modules and commands", "", "One line per module: its docstring, its first public names (`fn`, `+` means more), the commands it registers (`cmd`) and its tests (`test`). Bridge tests are `bridge/tests/test_<name>.py`; vitest ones are `test/<name>.test.ts`. A module with no `test` is covered only by the core tests (" + CORE_TESTS.map(testLabel).join(", ") + ").", ""];
  for (const [group, members] of groupBy(modules, (module) => module.group)) {
    out.push(`### ${group}/ (${members.length})`, "", ...members.map(moduleLine), "");
  }
  return out;
}

function commandIndex(modules: PythonModule[]): string[] {
  const pairs = modules.flatMap((module) => module.commands.map((name) => [name, module.name.replace(/\.py$/, "")] as const)).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return ["## Command index", "", `${pairs.length} commands, each as \`command@module\` (all in \`bridge/blendworks_bridge/commands/\`; \`npm run bench:tools\` lists the tools the MCP server derives from them):`, "", pairs.map(([name, module]) => `${name}@${module}`).join(" "), ""];
}

function sourceLine(source: TypeScriptSource): string {
  const name = basename(source.path);
  return `- \`${name}\`: ${source.description ?? `(exports ${source.exported.slice(0, 3).join(", ")})`}`;
}

function typeScriptSection(sources: TypeScriptSource[]): string[] {
  const out = ["## TypeScript sources, scripts and benchmarks", ""];
  for (const [group, members] of groupBy(sources, (source) => source.group)) out.push(`### ${group}/ (${members.length})`, "", ...members.map(sourceLine), "");
  return out;
}

function testsSection(tree: Tree): string[] {
  const tests = tree.tests;
  const stems = (names: string[], prefix: string): string => names.map((name) => name.replace(prefix, "").replace(/\.test\.ts$/, "").replace(/^test_/, "").replace(/\.py$/, "")).join(" ");
  const bridgeFolder = join(tree.root, "bridge", "tests");
  const helpers = existsSync(bridgeFolder) ? readdirSync(bridgeFolder).filter((name) => name.endsWith(".py") && !name.startsWith("test_")).sort() : [];
  const out = ["## Tests", ""];
  out.push(`- \`test/\` (vitest, ${tests.plain.length} files without Blender): ${stems(tests.plain, "test/")}`, "");
  out.push(`- \`test/\` (vitest, ${tests.blender.length} files that start Blender through \`useBlenderSlot()\`): ${stems(tests.blender, "test/")}`, "");
  out.push(`- \`bridge/tests/test_<name>.py\` (${tests.bridge.length} files, run inside Blender): ${stems(tests.bridge, "")}`, "");
  out.push(`- \`bridge/tests/\` helpers, not tests: ${helpers.join(" ")}`, "");
  return out;
}

const OVERVIEW = `# Code map

Generated by \`npx tsx scripts/codemap.mjs\` from the source tree; do not edit it. \`test/tooling/codemap.test.ts\` fails when it is stale (a module, command, test or script was added, removed or renamed), when a bridge module has no docstring line, or when it grows past ${MAX_MAP_BYTES / 1000} KB. Details live in the files it names: \`docs/DESIGN.md\` is the contract, \`CONTRIBUTING.md\` the rules, \`docs/LIMITS.md\` every named limit.

## Layers

- **MCP server** (\`src/mcp/\`): turns bridge commands into \`blender_<command>\` tools, routes and finds tools (\`routing/\`, \`blender_find_tools\`), runs the headless or desktop connection, installs into clients, and serves the Poly Haven library (\`src/mcp/library/\`). \`src/session.ts\` talks to the headless Blender session, \`src/blender.ts\` finds the Blender binary.
- **Bridge** (\`bridge/blendworks_bridge/\`): Python inside Blender. \`handler.py\` reads a request, \`registry.py\` holds every command, \`schema.py\` builds argument schemas, \`limits*.py\` hold the named limits, and the rest are the maths and builders the commands use. \`bridge/session.py\` is the headless entry point, \`bridge/addon/\` the desktop add-on.
- **Commands** (\`bridge/blendworks_bridge/commands/\`): one module per command family; each command is a function under \`@command(...)\`. \`bridge/blendworks_bridge/commands/__init__.py\` lists the modules that are imported.
- **Judge** (\`src/judge/\`, \`bridge/judge/\`, \`schemas/\`): checks an asset against a spec (\`docs/DESIGN.md\` sections 3 and 4): TypeScript stages and rules in \`src/judge/\`, Blender-side measurement in \`bridge/judge/\`. \`bridge/package/\` and \`src/package/\` build LOD packages.
- **Tests**: \`test/\` is vitest (some start Blender), \`bridge/tests/\` runs inside Blender through \`npm run test:bridge\`.
- **Scripts and benchmarks**: \`scripts/\` is the check, the fast check, the container check and their libraries (\`scripts/lib/\`); \`bench/\` holds benchmarks; \`docs/examples/\` builds whole example scenes with commands only.
`;

const HOW_TO_WORK = `## How to work

**Run one test.**
- One bridge test file: \`npm run test:bridge -- <part of the file name>\`, for example \`npm run test:bridge -- scene\`. Each \`test_*\` function gets a \`bridge\` fixture (\`bridge.ok("add_primitive", type="cube")\`, \`bridge.refuse("describe", "bad_args")\`) from \`bridge/tests/harness.py\`.
- One vitest file: \`npx vitest run test/judge/closeups.test.ts\`; add \`BLENDWORKS_FIXTURES=skip\` to skip judge fixture generation.
- While iterating: \`npm run check:fast\` (rules, typecheck, tests that need no Blender, and the tests related to your changed files by \`scripts/lib/fast-map.ts\`). The full \`npm run check\` only once, at the end, at low priority.

**Where things live.**
- Examples: \`docs/examples/*.py\` (run with \`blender --background --factory-startup --python docs/examples/<name>.py -- <out>\`), described in \`docs/examples/README.md\`, each run by a \`test/<area>-example.test.ts\`.
- Renders: tests and examples write only under the cache folder (\`.cache\`, or \`BLENDWORKS_CACHE\`; \`freshDir\` in \`test/judge/helpers.ts\`) or the OS temp folder; look at PNGs with the image reader. \`render_preview\` is for looking, \`render_final\` writes passes into the workspace.
- Limits: every schema bound is a named limit in \`bridge/blendworks_bridge/limits.py\`, \`limits_land.py\`, \`limits_parts.py\` and \`limits_parts_more.py\`, created with \`limit(key, value, unit, kind, reason)\` from \`limit_base.py\`; \`docs/LIMITS.md\` lists them all.
- Specs: \`jobs/<job>/SPEC.md\` (never edited); design contract \`docs/DESIGN.md\`; research notes \`docs/research/\`.

**The shared Blender and the memory gate.**
- At most \`BLENDWORKS_JOBS\` Blender processes run at once (default 2 on a desktop, from the CPU quota in a container); slots are a lock in the cache folder (\`scripts/lib/slots.ts\`). A vitest file that starts Blender calls \`useBlenderSlot()\` first.
- Bridge test files share Blender processes: \`bridge/tests/shared.py\` runs several files in one process with a full reset between them and compares a fingerprint afterwards, so a test must leave no state behind.
- The memory gate (\`scripts/lib/memory.ts\`, peaks in \`scripts/memory.json\`) starts a file only while the recorded peaks of the files holding slots plus its own fit 60 % of the memory limit (\`BLENDWORKS_MEMORY_BUDGET_MB\` overrides); a file with no record counts as at least 2 GB, and the first file always starts. Do not edit \`scripts/memory.json\` or \`scripts/durations.json\` in a job.

**Add a command.**
1. Create \`bridge/blendworks_bridge/commands/<name>.py\` with a docstring line and a function under \`@command("<name>", "<one short line>", properties, required, family=..., intents=[...], nearest=[...])\`; build the schema with \`schema.py\` and raise \`errors.py\` errors. Put the maths in a module beside it, not in the command.
2. Add \`"<name>"\` to \`MODULES\` in \`bridge/blendworks_bridge/commands/__init__.py\`; add a \`BRIDGE_MODULES\` row in \`scripts/lib/fast-map.ts\` only if the test is not named after the module.
3. Add \`bridge/tests/test_<name>.py\` and, for an MCP surface, the tool-selection entries in \`bench/tool-selection/\`; document it in \`docs/DESIGN.md\`.
4. Regenerate this map and \`docs/LIMITS.md\` (see below).

**Add a limit.** Define it with \`limit(...)\` in the limits module of its family, give it a kind (physical, memory, time, blender, protocol) and a reason, use it in the schema, then regenerate \`docs/LIMITS.md\` with \`blender -b --factory-startup --python bridge/tests/limits_doc.py\`; \`bridge/tests/test_world_scale.py\` fails when a bound has no named limit or the file is stale.

**Add a test.** Bridge: a \`test_*\` function in \`bridge/tests/test_<module>.py\` taking \`bridge\`, ending with \`run(globals())\`-style registration like its neighbours. Vitest: \`test/<name>.test.ts\`, with \`useBlenderSlot()\` at the top when it starts Blender and budgets from \`test/setup/work-clock.ts\`; never assert wall-clock bounds. Keep every source and test file at most 400 lines and write no code comments.

**Regenerate this map.** \`npx tsx scripts/codemap.mjs\` writes \`docs/CODEMAP.md\`; \`npx tsx scripts/codemap.mjs --check\` exits 1 when it is stale. Descriptions of TypeScript files are in \`docs/codemap-descriptions.json\`; descriptions of bridge modules are their docstring lines.
`;

export function buildMap(tree: Tree = repoTree()): string {
  const modules = pythonModules(tree);
  const sources = typeScriptSources(tree.root);
  const parts = [OVERVIEW, HOW_TO_WORK, ...[bridgeSection(modules), commandIndex(modules), typeScriptSection(sources), testsSection(tree)].map((lines) => lines.join("\n"))];
  return `${parts.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}

export function tooLarge(map: string): boolean {
  return Buffer.byteLength(map) > MAX_MAP_BYTES;
}

export function currentMap(root: string = repoRoot): string | undefined {
  return existsSync(join(root, MAP_PATH)) ? read(root, MAP_PATH) : undefined;
}
