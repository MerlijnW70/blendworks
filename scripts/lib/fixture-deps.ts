import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { repoRoot } from "./paths.js";

export const DEPENDENCY_VARIABLE = "FIXTURE_DEPS";
const DECLARATION = new RegExp(String.raw`^${DEPENDENCY_VARIABLE}\s*=\s*\(([^)]*)\)`, "m");
const IMPORT_LINE = /^\s*(?:import\s+([\w.,\s]+?)|from\s+([\w.]+)\s+import\s+[^\n]+)\s*(?:#.*)?$/gm;
const BRIDGE_PACKAGE = "bridge/blendworks_bridge";
const MODULE_FOLDERS = ["bridge/judge", "bridge"];

function posix(path: string): string {
  return path.split(sep).join("/");
}

export function declaredDependencies(script: string): string[] {
  const match = DECLARATION.exec(readFileSync(script, "utf8"));
  if (match === null) return [];
  return [...(match[1] ?? "").matchAll(/"([^"]+)"|'([^']+)'/g)].map((item) => item[1] ?? item[2] ?? "");
}

function topModules(source: string): string[] {
  const names: string[] = [];
  for (const match of source.matchAll(IMPORT_LINE)) {
    if (match[2] !== undefined) names.push(match[2]);
    else for (const part of (match[1] ?? "").split(",")) names.push(part.trim().split(/\s+/)[0] ?? "");
  }
  return [...new Set(names.map((name) => name.split(".")[0] ?? "").filter((name) => name !== ""))];
}

function resolveModule(name: string, base: string): string | undefined {
  if (name === "blendworks_bridge") return BRIDGE_PACKAGE;
  for (const folder of MODULE_FOLDERS) if (existsSync(join(base, folder, `${name}.py`))) return `${folder}/${name}.py`;
  return undefined;
}

export function importedProjectFiles(script: string, base: string = repoRoot): string[] {
  const found = new Set<string>();
  const visit = (source: string): void => {
    for (const name of topModules(source)) {
      const file = resolveModule(name, base);
      if (file === undefined || found.has(file)) continue;
      found.add(file);
      if (file.endsWith(".py")) visit(readFileSync(join(base, file), "utf8"));
    }
  };
  visit(readFileSync(script, "utf8"));
  return [...found].sort();
}

export function covers(declared: string[], file: string): boolean {
  return declared.some((entry) => entry === file || file.startsWith(`${entry}/`));
}

export function uncoveredImports(script: string, base: string = repoRoot): string[] {
  const declared = declaredDependencies(script);
  return importedProjectFiles(script, base).filter((file) => !covers(declared, file));
}

export function dependencyFiles(declared: string[], base: string = repoRoot): string[] {
  const out: string[] = [];
  const visit = (path: string): void => {
    if (statSync(join(base, path)).isDirectory()) {
      for (const entry of readdirSync(join(base, path), { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
        if ((entry.isDirectory() && entry.name !== "__pycache__") || entry.name.endsWith(".py")) visit(`${path}/${entry.name}`);
      }
    } else out.push(path);
  };
  for (const entry of [...declared].sort()) visit(entry);
  return out.map((file) => posix(relative(base, join(base, file))));
}

export function dependencyDigest(script: string, base: string = repoRoot): string[] {
  return dependencyFiles(declaredDependencies(script), base).map((file) => `dependency:${file}\n${readFileSync(join(base, file), "utf8")}`);
}

export function declarationAdvice(script: string, base: string = repoRoot): string[] {
  const missing = uncoveredImports(script, base);
  if (missing.length === 0) return [];
  const declared = [...declaredDependencies(script), ...missing].map((entry) => JSON.stringify(entry));
  const name = relative(base, script).split(sep).join("/");
  return [`${name} imports ${missing.join(", ")} but its cache key does not cover it: make its first line  ${DEPENDENCY_VARIABLE} = (${declared.join(", ")}${declared.length === 1 ? "," : ""})`];
}
