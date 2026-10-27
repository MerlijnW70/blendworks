import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const root = process.cwd();
const problems = [];

function walk(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === "__pycache__") continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...walk(path));
    else out.push(path);
  }
  return out;
}

const STRINGS = /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)/g;
const REGEX_LITERAL = /\/(?![/*])(?:\\.|[^/\n])+\/[a-z]*/g;

for (const file of [...walk(join(root, "src")), ...walk(join(root, "bridge")), ...walk(join(root, "test"))]) {
  const rel = relative(root, file).split(sep).join("/");
  if (!/\.(ts|py|mjs)$/.test(rel)) continue;
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n").length;
  if (lines > 400) problems.push(`${rel}: ${lines} lines, at most 400`);
  const code = text.replace(STRINGS, '""');
  const python = rel.endsWith(".py");
  const commented = python ? /(^|\s)#/m.test(code) : /\/\/|\/\*/.test(code.replace(REGEX_LITERAL, "/r/"));
  if (commented) problems.push(`${rel}: has a code comment`);
  if (python && /\b(exec|eval)\s*\(/.test(code) && !rel.includes("run_python")) problems.push(`${rel}: exec or eval outside the gated run_python command`);
}

const strictUtf8 = new TextDecoder("utf-8", { fatal: true });
const textFiles = [...readdirSync(root).map((name) => join(root, name)).filter((path) => statSync(path).isFile()), ...["src", "bridge", "test", "docs", "jobs", "schemas", "scripts"].flatMap((dir) => walk(join(root, dir)))];
for (const file of textFiles) {
  const rel = relative(root, file).split(sep).join("/");
  if (!/\.(ts|py|mjs|js|json|md|toml)$/.test(rel)) continue;
  try {
    strictUtf8.decode(readFileSync(file));
  } catch {
    problems.push(`${rel}: not valid UTF-8`);
  }
}

const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const allowedRuntime = ["@modelcontextprotocol/sdk", "zod"];
const allowedDev = ["@types/node", "tsx", "typescript", "vitest"];
for (const name of Object.keys(pkg.dependencies ?? {})) if (!allowedRuntime.includes(name)) problems.push(`package.json: ${name} is not an allowed runtime dependency`);
for (const name of Object.keys(pkg.devDependencies ?? {})) if (!allowedDev.includes(name)) problems.push(`package.json: ${name} is not an allowed dev dependency`);

if (problems.length > 0) {
  for (const problem of problems) console.error(problem);
  process.exit(1);
}
console.log("rules ok");
