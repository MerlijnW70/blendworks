import { pythonShape } from "./python-shape.js";

export type Mutant = { file: string; text: string; lines: number[]; functions: number };

export const MUTANT_MESSAGE = "planted bug in";

export function mutatePython(file: string, text: string): Mutant {
  const shape = pythonShape(text);
  const lines = text.split("\n");
  const inserts: { at: number; line: string }[] = [];
  for (const fn of shape.functions) {
    const first = fn.body[0];
    if (first === undefined) continue;
    const body = lines[first] ?? "";
    const indent = body.slice(0, body.length - body.trimStart().length);
    inserts.push({ at: first, line: `${indent}if not getattr(globals().get("__spec__"), "_initializing", False): raise RuntimeError(${JSON.stringify(`${MUTANT_MESSAGE} ${file}`)})` });
  }
  return apply(file, lines, inserts, []);
}

const FUNCTION_HEAD = /^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*[\w$]*\s*(?:<[^>]*>)?\(.*\)\s*(?::\s*[^={]+)?\{\s*$/;
const METHOD_HEAD = /^\s+(?:(?:public|private|protected|static|async|override|readonly|get|set)\s+)*[A-Za-z_$][\w$]*\s*(?:<[^>]*>)?\(.*\)\s*(?::\s*[^={]+)?\{\s*$/;
const ARROW_BODY = /=>\s*\{\s*$/;
const KEYWORD = /^\s*(?:if|for|while|switch|catch|with|else|do|try|return|function)\b/;

export function mutateScript(file: string, text: string): Mutant {
  const typed = file.endsWith(".ts") || file.endsWith(".mts");
  const armed = typed ? "(globalThis as { __blendworksArmed?: Set<string> }).__blendworksArmed" : "globalThis.__blendworksArmed";
  const lines = text.split("\n");
  const inserts: { at: number; line: string }[] = [];
  lines.forEach((line, index) => {
    const head = FUNCTION_HEAD.test(line) || ARROW_BODY.test(line) || (METHOD_HEAD.test(line) && !KEYWORD.test(line));
    if (!head) return;
    const next = lines[index + 1] ?? "";
    const indent = next.trim() === "" || next.trim().startsWith("}") ? `${line.slice(0, line.length - line.trimStart().length)}  ` : next.slice(0, next.length - next.trimStart().length);
    inserts.push({ at: index + 1, line: `${indent}if (${armed}?.has(${JSON.stringify(file)})) throw new Error(${JSON.stringify(`${MUTANT_MESSAGE} ${file}`)});` });
  });
  return apply(file, lines, inserts, [`(${armed} ??= new Set()).add(${JSON.stringify(file)});`]);
}

function apply(file: string, lines: string[], inserts: { at: number; line: string }[], tail: string[]): Mutant {
  const out: string[] = [];
  const changed: number[] = [];
  const byLine = new Map<number, string[]>();
  for (const insert of inserts) byLine.set(insert.at, [...(byLine.get(insert.at) ?? []), insert.line]);
  lines.forEach((line, index) => {
    for (const added of byLine.get(index) ?? []) {
      out.push(added);
      changed.push(out.length);
    }
    out.push(line);
  });
  const trailing = out.length > 0 && out[out.length - 1] === "" ? out.pop() : undefined;
  for (const added of tail) {
    out.push(added);
    changed.push(out.length);
  }
  if (trailing !== undefined) out.push(trailing);
  return { file, text: out.join("\n"), lines: changed, functions: inserts.length };
}

export function mutate(file: string, text: string): Mutant {
  return file.endsWith(".py") ? mutatePython(file, text) : mutateScript(file, text);
}
