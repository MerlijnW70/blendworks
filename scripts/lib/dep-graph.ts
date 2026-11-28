import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { posix } from "node:path";
import { FIXTURE_SCRIPT } from "./fixtures.js";
import { repoRoot } from "./paths.js";

export type Edge = "import" | "path" | "command" | "every command" | "loads" | "fixture" | "native library";

export type Graph = {
  files: string[];
  edges: Map<string, Map<string, Edge>>;
  hub: Map<string, Map<string, Edge>>;
  commands: Map<string, string>;
  commandModules: string[];
  native: Set<string>;
};

export type Source = { files: string[]; read: (file: string) => string | undefined };

const TEXT = /\.(ts|mts|mjs|js|cjs|py|json|md|toml|txt|sh|awk|ya?ml|cfg|ini)$/;
const SCRIPT = /\.(ts|mts|mjs|js|cjs)$/;
const COMMAND_PACKAGE = "bridge/blendworks_bridge/commands/";
const HUB = `${COMMAND_PACKAGE}__init__.py`;
const PYTHON_ROOTS = ["bridge", "bridge/judge", "bridge/package", "bridge/tests"];
const ITERATES_COMMANDS = /for\s+\w+(?:\s*,\s*\w+)?\s+in\s+[^:\n]*(?:COMMANDS|registry\.names\(\))|(?:sorted|set|list)\(COMMANDS\)|\bMODULES\b/;
const RUNS_ANY = /\.run\(|\.handle\(|\b(?:ok|call|refuse)\(\s*[a-z_]\w*\s*[,)]/;
const DISPATCH = "bridge/blendworks_bridge/";
const CATALOGUE = 20;
const DISPATCH_CORE = [`${DISPATCH}handler.py`, `${DISPATCH}registry.py`, HUB];
const STRING = /"""([\s\S]*?)"""|'''([\s\S]*?)'''|"((?:\\.|[^"\\\n])*)"|'((?:\\.|[^'\\\n])*)'|`((?:\\.|[^`\\])*)`/g;
const PYTHON_STRING = /"""([\s\S]*?)"""|'''([\s\S]*?)'''|"((?:\\.|[^"\\\n])*)"|'((?:\\.|[^'\\\n])*)'/g;
const CODE = /\.(ts|mts|mjs|js|cjs|py|sh|awk)$/;
const WALKS = /\bwalk\(|os\.walk|readdirSync\([^;\n]*recursive:\s*true|rglob|\*\*\//;
const RELATIVE_PATH = /^(\.\.?\/)*[\w@.-]*\w[\w@.-]*(\/[\w@.-]*\w[\w@.-]*)+\/?$/;
const JOIN_CALL =/\b(?:join|resolve|new URL)\(/g;

export function repoSource(root: string = repoRoot): Source {
  const listed = execFileSync("git", ["ls-files", "-co", "--exclude-standard", "-z"], { cwd: root, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  const files = listed.split("\0").filter((file) => file !== "" && existsSync(posix.join(root, file)) && statSync(posix.join(root, file)).isFile()).sort();
  const known = new Set(files);
  return { files, read: (file) => (TEXT.test(file) && known.has(file) ? readFileSync(posix.join(root, file), "utf8") : undefined) };
}

export function stringLiterals(text: string, python = false): string[] {
  const out: string[] = [];
  for (const match of text.matchAll(python ? PYTHON_STRING : STRING)) out.push(match[1] ?? match[2] ?? match[3] ?? match[4] ?? match[5] ?? "");
  return out;
}

class Index {
  readonly fileSet: Set<string>;
  readonly byName = new Map<string, string[]>();
  readonly dirs = new Map<string, string[]>();

  constructor(readonly files: string[]) {
    this.fileSet = new Set(files);
    for (const file of files) {
      const name = posix.basename(file);
      this.byName.set(name, [...(this.byName.get(name) ?? []), file]);
      const parts = file.split("/");
      for (let depth = 1; depth < parts.length; depth += 1) {
        const dir = parts.slice(0, depth).join("/");
        this.dirs.set(dir, [...(this.dirs.get(dir) ?? []), file]);
      }
    }
  }

  inside(dir: string, recursive: boolean): string[] {
    if (this.fileSet.has(`${dir}/__init__.py`)) return [];
    const all = this.dirs.get(dir) ?? [];
    return recursive ? all : all.filter((file) => posix.dirname(file) === dir);
  }

  path(path: string, recursive: boolean): string[] {
    const clean = posix.normalize(path).replace(/\/$/, "");
    if (clean.startsWith("..") || clean === ".") return [];
    if (this.fileSet.has(clean)) return [clean];
    return this.inside(clean, recursive);
  }

  suffix(segments: string[], recursive: boolean): string[] {
    const parts = segments.flatMap((segment) => segment.split("/")).filter((part) => part !== "" && part !== "." && part !== "..");
    if (parts.length === 0) return [];
    const distAt = parts.indexOf("dist");
    if (distAt >= 0 && distAt < parts.length - 1) return this.fromDist(parts.slice(distAt + 1));
    const tail = parts.join("/");
    const out = new Set<string>();
    for (const file of this.files) if (file === tail || file.endsWith(`/${tail}`)) out.add(file);
    for (const dir of this.dirs.keys()) if (dir === tail || dir.endsWith(`/${tail}`)) for (const file of this.inside(dir, recursive)) out.add(file);
    return [...out];
  }

  fromDist(parts: string[]): string[] {
    const stem = parts.join("/").replace(/\.(js|d\.ts)$/, "");
    const source = `src/${stem}.ts`;
    if (this.fileSet.has(source)) return [source];
    return this.dirs.get(`src/${stem}`) ?? [];
  }
}

function resolveScriptImport(from: string, specifier: string, index: Index): string[] {
  if (!specifier.startsWith(".")) return [];
  const base = posix.normalize(posix.join(posix.dirname(from), specifier));
  const candidates = [base, base.replace(/\.js$/, ".ts"), base.replace(/\.mjs$/, ".mts"), `${base}.ts`, `${base}/index.ts`, base.replace(/\.js$/, ".tsx")];
  const found = candidates.find((candidate) => index.fileSet.has(candidate));
  return found === undefined ? [] : [found];
}

const SCRIPT_IMPORTS = [/\bimport\s+(?:type\s+)?[^"'`;]*?from\s*["']([^"']+)["']/g, /\bexport\s+[^"'`;]*?from\s*["']([^"']+)["']/g, /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g, /\bimport\s+["']([^"']+)["']/g, /\bvi\.mock\(\s*["']([^"']+)["']/g, /\brequire\(\s*["']([^"']+)["']\s*\)/g];

function scriptImports(file: string, text: string, index: Index): string[] {
  const out: string[] = [];
  for (const pattern of SCRIPT_IMPORTS) for (const match of text.matchAll(pattern)) out.push(...resolveScriptImport(file, match[1] ?? "", index));
  return out;
}

function pythonModule(name: string, roots: string[], index: Index): string | undefined {
  const path = name.split(".").join("/");
  for (const root of roots) {
    for (const candidate of [`${root}/${path}.py`, `${root}/${path}/__init__.py`]) if (index.fileSet.has(posix.normalize(candidate))) return posix.normalize(candidate);
  }
  return undefined;
}

function pythonImports(file: string, text: string, index: Index): string[] {
  const here = posix.dirname(file);
  const roots = [here, ...searchRoots(file, text, index), ...PYTHON_ROOTS];
  const out = new Set<string>();
  const add = (found: string | undefined): void => {
    if (found !== undefined) out.add(found);
  };
  for (const match of text.matchAll(/^[ \t]*import[ \t]+([\w.]+(?:[ \t]+as[ \t]+\w+)?(?:[ \t]*,[ \t]*[\w.]+(?:[ \t]+as[ \t]+\w+)?)*)/gm)) {
    for (const part of (match[1] ?? "").split(",")) {
      const name = part.trim().split(/\s+/)[0] ?? "";
      const pieces = name.split(".");
      for (let depth = 1; depth <= pieces.length; depth += 1) add(pythonModule(pieces.slice(0, depth).join("."), roots, index));
    }
  }
  for (const match of text.matchAll(/^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]+)/gm)) {
    const dots = (match[1] ?? "").length;
    const name = match[2] ?? "";
    const names = (match[3] ?? "").replace(/[()]/g, "").split(",").map((part) => part.trim().split(/\s+/)[0] ?? "").filter((part) => /^\w+$/.test(part));
    const bases = dots > 0 ? [posix.normalize(posix.join(here, ...Array.from({ length: dots - 1 }, () => "..")))] : roots;
    const pieces = name === "" ? [] : name.split(".");
    for (const base of bases) {
      for (let depth = 1; depth <= pieces.length; depth += 1) add(pythonModule(pieces.slice(0, depth).join("."), [base], index));
      const module = pieces.join("/");
      for (const item of names) add(pythonModule([module, item].filter((part) => part !== "").join("/").split("/").join("."), [base], index));
      if (dots > 0 && pieces.length === 0) add(pythonModule("__init__", [base], index));
    }
  }
  return [...out];
}

export function callArguments(text: string, open: number): string[] {
  const args: string[] = [];
  let depth = 0;
  let quote: string | undefined;
  let current = "";
  for (let at = open; at < text.length; at += 1) {
    const char = text[at] as string;
    if (quote !== undefined) {
      current += char;
      if (char === "\\") {
        current += text[at + 1] ?? "";
        at += 1;
      } else if (char === quote) quote = undefined;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") {
      quote = char;
      current += char;
    } else if (char === "(" || char === "[" || char === "{") {
      depth += 1;
      if (depth > 1) current += char;
    } else if (char === ")" || char === "]" || char === "}") {
      depth -= 1;
      if (depth === 0) {
        args.push(current.trim());
        return args;
      }
      current += char;
    } else if (char === "," && depth === 1) {
      args.push(current.trim());
      current = "";
    } else if (depth >= 1) current += char;
  }
  return args;
}

type Joined = { segments: string[]; searchRoot: boolean };

function joinedPaths(text: string, python: boolean): Joined[] {
  const out: Joined[] = [];
  for (const call of text.matchAll(JOIN_CALL)) {
    const start = call.index ?? 0;
    const lineStart = text.lastIndexOf("\n", start) + 1;
    const before = text.slice(lineStart, start);
    const assigned = /^\s*(\w+)\s*=/.exec(before)?.[1];
    const searchRoot = python && (/sys\.path\.(insert|append)\(/.test(before) || (assigned !== undefined && new RegExp(String.raw`sys\.path\.(insert|append)\([^)\n]*\b${assigned}\b`).test(text)));
    let run: string[] = [];
    const flush = (): void => {
      if (run.length > 0) out.push({ segments: run, searchRoot });
      run = [];
    };
    for (const arg of callArguments(text, start + call[0].length - 1)) {
      const literal = /^["'`]([^"'`$]*)["'`]$/.exec(arg);
      if (literal === null) flush();
      else run.push(literal[1] ?? "");
    }
    flush();
  }
  return out;
}

function pathReferences(file: string, text: string, index: Index): string[] {
  const python = file.endsWith(".py");
  const recursive = WALKS.test(text);
  const out = new Set<string>();
  const here = posix.dirname(file);
  for (const literal of stringLiterals(text, python)) {
    if (literal.length === 0 || literal.length > 200 || /\s/.test(literal)) continue;
    if (literal.includes("/")) {
      if (!RELATIVE_PATH.test(literal) || (python && /^\.\.?\//.test(literal))) continue;
      const parts = literal.split("/").filter((part) => part !== "");
      const distAt = parts.indexOf("dist");
      if (distAt >= 0 && distAt < parts.length - 1) for (const found of index.fromDist(parts.slice(distAt + 1))) out.add(found);
      for (const found of [...index.path(posix.join(here, literal), recursive), ...index.path(literal, recursive)]) out.add(found);
    } else if (/^[\w.-]+\.[A-Za-z]\w*$/.test(literal)) {
      for (const found of index.byName.get(literal) ?? []) out.add(found);
    }
  }
  for (const joined of joinedPaths(text, python)) {
    if (joined.searchRoot) continue;
    for (const item of joinedTargets(here, joined.segments, index, recursive)) out.add(item);
  }
  out.delete(file);
  return [...out];
}

function joinedTargets(here: string, segments: string[], index: Index, recursive: boolean): string[] {
  const joined = segments.join("/");
  const parts = joined.split("/").filter((part) => part !== "" && part !== ".");
  if (parts.every((part) => part === "..")) return [];
  if (/^\.\.?\//.test(joined) || parts[0] === "..") return index.path(posix.join(here, joined), recursive);
  return parts.length >= 2 ? index.suffix(parts, recursive) : index.path(parts[0] ?? ".", recursive);
}

function searchRoots(file: string, text: string, index: Index): string[] {
  const roots = new Set<string>();
  for (const joined of joinedPaths(text, true)) {
    if (!joined.searchRoot) continue;
    for (const found of joinedTargets(posix.dirname(file), joined.segments, index, false)) roots.add(posix.dirname(found));
    const parts = joined.segments.join("/").split("/").filter((part) => part !== "" && part !== "." && part !== "..");
    const tail = parts.join("/");
    for (const dir of index.dirs.keys()) if (tail !== "" && (dir === tail || dir.endsWith(`/${tail}`))) roots.add(dir);
  }
  return [...roots];
}

export function commandNames(files: string[], read: (file: string) => string | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const file of files.filter((name) => name.startsWith(COMMAND_PACKAGE) && name.endsWith(".py"))) {
    for (const match of (read(file) ?? "").matchAll(/@command\(\s*["']([A-Za-z0-9_]+)["']/g)) out.set(match[1] ?? "", file);
  }
  return out;
}

function commandUses(text: string, commands: Map<string, string>, python: boolean): string[] {
  const out = new Set<string>();
  for (const literal of stringLiterals(text, python)) {
    const name = literal.startsWith("blender_") ? literal.slice("blender_".length) : literal;
    const module = commands.get(name);
    if (module !== undefined) out.add(module);
    for (const tool of literal.matchAll(/\bblender_([a-z0-9_]+)/g)) {
      const found = commands.get(tool[1] ?? "");
      if (found !== undefined) out.add(found);
    }
  }
  return [...out];
}

export function hubModules(read: (file: string) => string | undefined, index: { fileSet: Set<string> }): string[] {
  const text = read(HUB) ?? "";
  const block = /MODULES\s*=\s*\(([^)]*)\)/.exec(text)?.[1] ?? "";
  return stringLiterals(block, true).map((name) => `${COMMAND_PACKAGE}${name}.py`).filter((file) => index.fileSet.has(file));
}

export function buildGraph(source: Source = repoSource()): Graph {
  const index = new Index(source.files);
  const commands = commandNames(source.files, source.read);
  const commandModules = [...new Set(commands.values())].sort();
  const fixtureScripts = fixtureScriptsOf(source.files);
  const edges = new Map<string, Map<string, Edge>>();
  const link = (from: string, to: string, kind: Edge): void => {
    if (from === to) return;
    const out = edges.get(from) ?? new Map<string, Edge>();
    if (!out.has(to)) out.set(to, kind);
    edges.set(from, out);
  };
  for (const file of source.files) {
    const text = source.read(file);
    if (text === undefined) continue;
    if (SCRIPT.test(file)) for (const target of scriptImports(file, text, index)) link(file, target, "import");
    if (file.endsWith(".py")) for (const target of pythonImports(file, text, index)) link(file, target, "import");
    if (CODE.test(file)) for (const target of pathReferences(file, text, index)) link(file, target, "path");
    const callsByName = !file.startsWith(DISPATCH) || (!DISPATCH_CORE.includes(file) && /\bCOMMANDS\b/.test(text));
    const used = callsByName && (CODE.test(file) || file.endsWith(".json")) ? commandUses(text, commands, file.endsWith(".py")) : [];
    if (!(file.startsWith("src/") && used.length > CATALOGUE)) for (const target of used) link(file, target, "command");
    if (CODE.test(file)) {
      const literals = new Set(stringLiterals(text, file.endsWith(".py")));
      for (const target of fixtureScripts) if (literals.has(posix.basename(target, ".py"))) link(file, target, "fixture");
    }
    if (ITERATES_COMMANDS.test(text) && RUNS_ANY.test(text) && !file.startsWith(DISPATCH)) for (const target of commandModules) link(file, target, "every command");
  }
  const hub = new Map<string, Map<string, Edge>>([[HUB, new Map(hubModules(source.read, index).map((file) => [file, "loads" as Edge]))]]);
  const crates = nativeCrates(source);
  for (const file of source.files) {
    const text = CODE.test(file) && !crates.files.has(file) ? source.read(file) : undefined;
    if (text === undefined) continue;
    const literals = new Set(stringLiterals(text, file.endsWith(".py")));
    for (const crate of crates.list) if (crate.libraries.some((name) => literals.has(name))) for (const target of crate.files) link(file, target, "native library");
  }
  return { files: source.files, edges, hub, commands, commandModules, native: crates.files };
}

export type Reach = Map<string, { via: string; kind: Edge }>;

export function dependents(graph: Graph, target: string, withHub: boolean, stop: (file: string) => boolean = () => false): Reach {
  const reverse = new Map<string, Array<[string, Edge]>>();
  const add = (map: Map<string, Map<string, Edge>>): void => {
    for (const [from, out] of map) for (const [to, kind] of out) reverse.set(to, [...(reverse.get(to) ?? []), [from, kind]]);
  };
  add(graph.edges);
  if (withHub) add(graph.hub);
  const seen: Reach = new Map();
  const queue = [target];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const [from, kind] of reverse.get(current) ?? []) {
      if (from === target || seen.has(from)) continue;
      seen.set(from, { via: current, kind });
      if (!stop(from)) queue.push(from);
    }
  }
  return seen;
}

export function dependencies(graph: Graph, start: string, withHub: boolean): Set<string> {
  const seen = new Set<string>([start]);
  const queue = [start];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    const next = [...(graph.edges.get(current)?.keys() ?? []), ...(withHub ? (graph.hub.get(current)?.keys() ?? []) : [])];
    for (const file of next) {
      if (seen.has(file)) continue;
      seen.add(file);
      queue.push(file);
    }
  }
  return seen;
}

export type Crate = { libraries: string[]; files: string[] };

export function nativeCrates(source: Source): { list: Crate[]; files: Set<string> } {
  const list: Crate[] = [];
  for (const manifest of source.files.filter((file) => posix.basename(file) === "Cargo.toml")) {
    const text = source.read(manifest) ?? "";
    const lib = /\[lib\][^[]*?\bname\s*=\s*"([^"]+)"/.exec(text)?.[1] ?? /\[package\][^[]*?\bname\s*=\s*"([^"]+)"/.exec(text)?.[1];
    if (lib === undefined) continue;
    const name = lib.replace(/-/g, "_");
    const dir = posix.dirname(manifest);
    list.push({ libraries: [`${name}.dll`, `lib${name}.so`, `lib${name}.dylib`], files: source.files.filter((file) => dir === "." || file.startsWith(`${dir}/`)) });
  }
  return { list, files: new Set(list.flatMap((crate) => crate.files)) };
}

export function fixtureScriptsOf(files: string[]): string[] {
  return files.filter((name) => posix.dirname(name) === "test/judge" && FIXTURE_SCRIPT.test(posix.basename(name)));
}

export function pythonResolver(files: Iterable<string>): (from: string, dots: number, name: string) => string | undefined {
  const fileSet = new Set(files);
  return (from, dots, name) => {
    const here = posix.dirname(from);
    const roots = dots > 0 ? [posix.normalize(posix.join(here, ...Array.from({ length: dots - 1 }, () => "..")))] : [here, ...PYTHON_ROOTS];
    const path = name === "" ? "__init__" : name.split(".").join("/");
    for (const root of roots) {
      for (const candidate of [`${root}/${path}.py`, `${root}/${path}/__init__.py`]) {
        const clean = posix.normalize(candidate);
        if (fileSet.has(clean)) return clean;
      }
    }
    return undefined;
  };
}
