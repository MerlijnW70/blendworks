import { execFileSync } from "node:child_process";
import { posix } from "node:path";
import { buildGraph, dependencies, dependents, fixtureScriptsOf, type Graph, pythonResolver, repoSource, type Source } from "./dep-graph.js";
import { repoRoot } from "./paths.js";
import { importTimeKeys, pythonShape, type PyShape } from "./python-shape.js";

export const BLENDER_MARKER = "useBlenderSlot(";
export const PACKAGE = "bridge/blendworks_bridge/";

export const SHARED: [RegExp, string][] = [
  [/^(package\.json|package-lock\.json|tsconfig(\.build)?\.json|vitest\.config\.ts|\.gitignore|\.gitattributes|\.npmrc)$/, "package files"],
  [/^docker\//, "Docker files"],
  [/^test\/setup\//, "the vitest harness"],
  [/^bridge\/tests\/(harness|shared|fingerprint)\.py$/, "the bridge test harness"],
  [/^scripts\/(check|check-affected|check-fast|check-watch|bridge-tests|rules|mutation-study)\.mjs$/, "the runner"],
  [/^scripts\/(durations|memory)\.json$/, "the runner's records"],
  [/^scripts\/lib\/(affected|affected-check|blender-check|bridge-runner|bridge-shared|checks|dep-graph|durations|entry-cache|file-limits|fixture-deps|fixtures|heartbeat|locks|memory|memory-meter|pass-list|paths|pipeline|progress|python-shape|run|slot-wait|slots|timings|wall-clock-lint)\.ts$/, "the runner"],
  [/^src\/blender\.ts$/, "the runner (Blender lookup, slots and threads)"],
  [/^bridge\/blendworks_bridge\/(handler|registry|schema|limits\w*|limit_base|kit_limits|__init__|commands\/__init__)\.py$/, "the bridge handler, registry, schema and limits"],
  [/^schemas\//, "schema"],
];

export const CORE_VITEST = ["test/mcp-e2e.test.ts", "test/session.test.ts", "test/tooling/codemap.test.ts"];
export const CORE_BRIDGE = ["bridge/tests/test_smoke.py", "bridge/tests/test_describe.py", "bridge/tests/test_crate.py"];

export type Change = { file: string; status: "A" | "M" | "D" | "R"; baseLines: number[]; headLines: number[] };

export type Tests = { vitest: string[]; blender: string[]; bridge: string[] };

export type Selection = { vitest: string[]; bridge: string[]; everything: boolean; fixtures: boolean; reasons: string[]; byChange: Map<string, string[]> };

export const FIXTURE_BUILD = "the judge fixture build (vitest global setup)";

export type Repo = { source: Source; graph: Graph; base: (file: string) => string | undefined };

export function isTestFile(file: string): boolean {
  return /^test\/.*\.test\.ts$/.test(file) || /^bridge\/tests\/test_[^/]*\.py$/.test(file);
}

export function discoverTests(source: Source): Tests {
  const vitest = source.files.filter((file) => /^test\/.*\.test\.ts$/.test(file));
  return { vitest, blender: vitest.filter((file) => (source.read(file) ?? "").includes(BLENDER_MARKER)), bridge: source.files.filter((file) => /^bridge\/tests\/test_[^/]*\.py$/.test(file)) };
}

export function sharedReason(file: string): string | undefined {
  return SHARED.find(([pattern]) => pattern.test(file))?.[1];
}

const DOCUMENT = /^(docs\/.*|jobs\/.*|[^/]+)\.md$/;
const CODE = /\.(ts|mts|mjs|js|cjs|py|sh|awk)$/;

export type Mode = { withHub: boolean; why: string };

function packageShapes(repo: Repo): Map<string, { shape: PyShape; text: string }> {
  const out = new Map<string, { shape: PyShape; text: string }>();
  for (const file of repo.source.files) {
    if (!file.startsWith(PACKAGE) || !file.endsWith(".py")) continue;
    const text = repo.source.read(file) ?? "";
    out.set(file, { shape: pythonShape(text), text });
  }
  return out;
}

export function changeMode(change: Change, repo: Repo, importTime: () => Set<string>): Mode {
  if (repo.graph.native.has(change.file)) return { withHub: false, why: "native code, which runs when a kernel is called" };
  if (!change.file.startsWith(PACKAGE) || !change.file.endsWith(".py")) return { withHub: true, why: "loaded" };
  if (change.status !== "M") return { withHub: true, why: "new module" };
  const headText = repo.source.read(change.file) ?? "";
  const baseText = repo.base(change.file) ?? "";
  const sides: [PyShape, string[], number[]][] = [
    [pythonShape(headText), headText.split("\n"), change.headLines],
    [pythonShape(baseText), baseText.split("\n"), change.baseLines],
  ];
  const touched = new Set<string>();
  for (const [shape, lines, numbers] of sides) {
    for (const number of numbers) {
      const index = number - 1;
      if ((lines[index] ?? "").trim() === "") continue;
      const owner = shape.owner[index];
      if (owner !== undefined) {
        touched.add(owner);
        continue;
      }
      const header = shape.headerOf[index];
      const fn = shape.functions.find((item) => item.name === header && item.header.includes(index));
      if (fn !== undefined && fn.plainHeader) {
        touched.add(fn.name);
        continue;
      }
      return { withHub: true, why: `line ${number} runs when the module loads` };
    }
  }
  const keys = importTime();
  const early = [...touched].filter((name) => keys.has(`${change.file}:${name}`) || keys.has(`${change.file}:${name.split(".")[0] ?? name}`));
  if (early.length > 0) return { withHub: true, why: `${early.slice(0, 3).join(", ")} can run when modules load` };
  return { withHub: false, why: `only the bodies of ${[...touched].slice(0, 4).join(", ")}${touched.size > 4 ? ", ..." : ""}` };
}

function short(files: string[], most = 8): string {
  return files.length <= most ? files.join(", ") : `${files.slice(0, most).join(", ")} and ${files.length - most} more`;
}

export function selectAffected(changes: Change[], repo: Repo): Selection {
  const tests = discoverTests(repo.source);
  const allTests = new Set([...tests.vitest, ...tests.bridge]);
  const picked = new Set<string>();
  const reasons: string[] = [];
  const byChange = new Map<string, string[]>();
  let everything = false;
  let fixtures = false;
  const scripts = new Set(fixtureScriptsOf(repo.source.files));
  let names: Set<string> | undefined;
  const importTime = (): Set<string> => (names ??= importTimeKeys(packageShapes(repo), pythonResolver(repo.source.files)));
  const stop = (file: string): boolean => sharedReason(file) !== undefined && !file.startsWith("bridge/");
  for (const change of changes) {
    const shared = sharedReason(change.file);
    if (change.status === "D" || change.status === "R") {
      everything = true;
      reasons.push(`${change.file}: ${change.status === "D" ? "deleted" : "renamed"}, so its old dependents cannot be traced -> everything`);
      continue;
    }
    if (shared !== undefined) {
      everything = true;
      reasons.push(`${change.file}: ${shared} -> everything`);
      continue;
    }
    const mode = changeMode(change, repo, importTime);
    const reach = dependents(repo.graph, change.file, mode.withHub, stop);
    const found = [...reach.keys()].filter((file) => allTests.has(file));
    if (allTests.has(change.file)) found.unshift(change.file);
    byChange.set(change.file, found);
    if (scripts.has(change.file) || [...reach.keys()].some((file) => scripts.has(file))) {
      if (!fixtures) reasons.push(`${change.file}: a judge fixture script depends on it -> ${FIXTURE_BUILD}`);
      fixtures = true;
    }
    if (found.length === 0 && !CODE.test(change.file) && !DOCUMENT.test(change.file)) {
      everything = true;
      reasons.push(`${change.file}: no test reads it by a name or path the map can see -> everything`);
      continue;
    }
    for (const file of found) picked.add(file);
    const how = mode.withHub ? "what loads it" : `what calls it (${mode.why})`;
    reasons.push(found.length === 0 ? `${change.file}: no test loads or reads it` : `${change.file}: ${mode.withHub && mode.why !== "loaded" ? `${mode.why}; ` : ""}${how} -> ${found.length} tests: ${short(found)}`);
  }
  if (everything) return { vitest: [...tests.vitest], bridge: [...tests.bridge], everything, fixtures: true, reasons, byChange };
  const plain = tests.vitest.filter((file) => !tests.blender.includes(file));
  const vitest = [...new Set([...plain, ...CORE_VITEST.filter((file) => allTests.has(file)), ...[...picked].filter((file) => file.startsWith("test/"))])].sort();
  const bridge = [...new Set([...CORE_BRIDGE.filter((file) => allTests.has(file)), ...[...picked].filter((file) => file.startsWith("bridge/"))])].sort();
  const usesFixtures = vitest.some((file) => [...dependencies(repo.graph, file, false)].some((dep) => scripts.has(dep)));
  return { vitest, bridge, everything, fixtures: fixtures || usesFixtures, reasons, byChange };
}

function git(args: string[], root: string): string {
  return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], maxBuffer: 256 * 1024 * 1024 });
}

export function mergeBase(ref: string | undefined, root: string = repoRoot): string {
  const candidates = ref === undefined ? ["origin/main", "main"] : [ref];
  for (const candidate of candidates) {
    try {
      return git(["merge-base", "HEAD", candidate], root).trim();
    } catch {
      continue;
    }
  }
  if (ref !== undefined) throw new Error(`cannot find a merge base of HEAD and ${ref}`);
  return git(["rev-parse", "HEAD"], root).trim();
}

export function parseHunks(diff: string): { baseLines: number[]; headLines: number[] } {
  const baseLines: number[] = [];
  const headLines: number[] = [];
  for (const match of diff.matchAll(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/gm)) {
    const [baseStart, baseCount, headStart, headCount] = [Number(match[1]), match[2] === undefined ? 1 : Number(match[2]), Number(match[3]), match[4] === undefined ? 1 : Number(match[4])];
    for (let line = 0; line < baseCount; line += 1) baseLines.push(baseStart + line);
    for (let line = 0; line < headCount; line += 1) headLines.push(headStart + line);
  }
  return { baseLines, headLines };
}

export function gitChanges(base: string, root: string = repoRoot, head?: string): Change[] {
  const out: Change[] = [];
  const range = head === undefined ? [base] : [base, head];
  const status = git(["diff", "--name-status", "-M", "-z", ...range], root).split("\0").filter((part) => part !== "");
  for (let at = 0; at < status.length; ) {
    const code = (status[at] as string)[0] as string;
    if (code === "R" || code === "C") {
      out.push({ file: status[at + 1] as string, status: "R", baseLines: [], headLines: [] });
      if (code === "C") out[out.length - 1] = { file: status[at + 2] as string, status: "A", baseLines: [], headLines: [] };
      else out.push({ file: status[at + 2] as string, status: "A", baseLines: [], headLines: [] });
      at += 3;
      continue;
    }
    const file = status[at + 1] as string;
    at += 2;
    if (code === "D") out.push({ file, status: "D", baseLines: [], headLines: [] });
    else if (code === "A") out.push({ file, status: "A", baseLines: [], headLines: [] });
    else out.push({ file, status: "M", ...parseHunks(git(["diff", "-U0", "--no-color", ...range, "--", file], root)) });
  }
  const untracked = head === undefined ? git(["ls-files", "--others", "--exclude-standard", "-z"], root).split("\0") : [];
  for (const file of untracked.filter((part) => part !== "")) out.push({ file, status: "A", baseLines: [], headLines: [] });
  const seen = new Set<string>();
  return out.filter((change) => !seen.has(change.file) && seen.add(change.file)).sort((a, b) => a.file.localeCompare(b.file));
}

export function workingRepo(base: string, root: string = repoRoot): Repo {
  const source = repoSource(root);
  return {
    source,
    graph: buildGraph(source),
    base: (file) => {
      try {
        return git(["show", `${base}:${file}`], root);
      } catch {
        return undefined;
      }
    },
  };
}

export function relativePosix(file: string): string {
  return posix.normalize(file.split("\\").join("/"));
}
