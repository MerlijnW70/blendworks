export type PyFunction = { name: string; owner: string; header: number[]; body: number[]; plainHeader: boolean; inClass: string | undefined };

export type PyShape = { lines: number; owner: (string | undefined)[]; headerOf: (string | undefined)[]; functions: PyFunction[]; importTime: string };

type Logical = { first: number; last: number; text: string; indent: number };

function logicalLines(text: string): Logical[] {
  const out: Logical[] = [];
  const physical = text.split("\n");
  let start = 0;
  let depth = 0;
  let quote: string | undefined;
  let buffer = "";
  for (let index = 0; index < physical.length; index += 1) {
    const line = physical[index] as string;
    if (buffer === "") start = index;
    buffer += `${line}\n`;
    let at = 0;
    let continued = false;
    while (at < line.length) {
      const char = line[at] as string;
      if (quote !== undefined) {
        if (char === "\\") at += 2;
        else if (line.startsWith(quote, at)) {
          at += quote.length;
          quote = undefined;
        } else at += 1;
        continue;
      }
      if (char === "#") break;
      if (line.startsWith('"""', at) || line.startsWith("'''", at)) {
        quote = line.slice(at, at + 3);
        at += 3;
      } else if (char === '"' || char === "'") {
        quote = char;
        at += 1;
      } else {
        if ("([{".includes(char)) depth += 1;
        else if (")]}".includes(char)) depth = Math.max(0, depth - 1);
        else if (char === "\\" && at === line.length - 1) continued = true;
        at += 1;
      }
    }
    if (quote !== undefined && quote.length === 1) quote = undefined;
    if (depth === 0 && quote === undefined && !continued) {
      const first = physical[start] as string;
      if (buffer.trim() !== "") out.push({ first: start, last: index, text: buffer, indent: first.length - first.trimStart().length });
      buffer = "";
    }
  }
  if (buffer.trim() !== "") {
    const first = physical[start] as string;
    out.push({ first: start, last: physical.length - 1, text: buffer, indent: first.length - first.trimStart().length });
  }
  return out;
}

type Block = { kind: "def" | "class"; indent: number; name: string; fn: PyFunction | undefined };

const DEF = /^\s*(?:async\s+)?def\s+(\w+)\s*\(([\s\S]*)\)\s*(?:->[\s\S]*?)?:\s*([\s\S]*)$/;
const CLASS = /^\s*class\s+(\w+)/;

export function stripStrings(text: string): string {
  return text.replace(/"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/g, '""').replace(/#[^\n]*/g, "");
}

export function pythonShape(text: string): PyShape {
  const lineCount = text.split("\n").length;
  const owner = new Array<string | undefined>(lineCount).fill(undefined);
  const headerOf = new Array<string | undefined>(lineCount).fill(undefined);
  const functions: PyFunction[] = [];
  const stack: Block[] = [];
  const importTime: string[] = [];
  for (const logical of logicalLines(text)) {
    while (stack.length > 0 && (stack[stack.length - 1] as Block).indent >= logical.indent) stack.pop();
    const outerDef = stack.find((block) => block.kind === "def");
    const range = Array.from({ length: logical.last - logical.first + 1 }, (_, offset) => logical.first + offset);
    if (outerDef !== undefined) {
      for (const line of range) owner[line] = outerDef.name;
      outerDef.fn?.body.push(...range);
    }
    const def = DEF.exec(logical.text);
    const cls = CLASS.exec(logical.text);
    if (def !== null) {
      const name = def[1] as string;
      const oneLine = (def[3] ?? "").trim() !== "";
      const inClass = stack.length > 0 && (stack[stack.length - 1] as Block).kind === "class" ? (stack[stack.length - 1] as Block).name : undefined;
      if (outerDef === undefined) {
        const qualified = inClass === undefined ? name : `${inClass}.${name}`;
        const fn: PyFunction = { name: qualified, owner: qualified, header: range, body: [], plainHeader: !oneLine && !/\(/.test(def[2] ?? ""), inClass };
        functions.push(fn);
        for (const line of range) headerOf[line] = qualified;
        if (oneLine || !fn.plainHeader) importTime.push(logical.text.replace(/^\s*(?:async\s+)?def\s+\w+/, ""));
        stack.push({ kind: "def", indent: logical.indent, name: qualified, fn });
      } else stack.push({ kind: "def", indent: logical.indent, name: outerDef.name, fn: undefined });
      continue;
    }
    if (cls !== null) {
      if (outerDef === undefined) importTime.push(logical.text.replace(/^\s*class\s+\w+/, ""));
      stack.push({ kind: "class", indent: logical.indent, name: cls[1] as string, fn: undefined });
      continue;
    }
    if (outerDef === undefined && !/^\s*(from\s+\S+\s+)?import\s/.test(logical.text)) importTime.push(logical.text);
  }
  return { lines: lineCount, owner, headerOf, functions, importTime: importTime.join("\n") };
}

export function identifiers(text: string): Set<string> {
  return new Set(stripStrings(text).match(/[A-Za-z_]\w*/g) ?? []);
}

export type Resolve = (from: string, dots: number, name: string) => string | undefined;

type Scope = { names: Map<string, [string, string]>; modules: Map<string, string>; star: string[] };

export function moduleScope(file: string, text: string, resolve: Resolve): Scope {
  const scope: Scope = { names: new Map(), modules: new Map(), star: [] };
  for (const match of text.matchAll(/^[ \t]*import[ \t]+([^\n]+)/gm)) {
    for (const part of (match[1] ?? "").split(",")) {
      const [dotted = "", alias] = part.trim().split(/\s+as\s+/);
      const top = dotted.split(".")[0] ?? "";
      const found = resolve(file, 0, alias === undefined ? top : dotted);
      if (found !== undefined) scope.modules.set(alias ?? top, found);
    }
  }
  for (const match of text.matchAll(/^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n]+)/gm)) {
    const dots = (match[1] ?? "").length;
    const base = match[2] ?? "";
    const module = resolve(file, dots, base);
    for (const part of (match[3] ?? "").replace(/[()]/g, "").split(",")) {
      const [name = "", alias] = part.trim().split(/\s+as\s+/);
      if (name === "") continue;
      if (name === "*") {
        if (module !== undefined) scope.star.push(module);
        continue;
      }
      const sub = resolve(file, dots, [base, name].filter((piece) => piece !== "").join("."));
      if (sub !== undefined && sub !== module) scope.modules.set(alias ?? name, sub);
      else if (module !== undefined) scope.names.set(alias ?? name, [module, name]);
    }
  }
  return scope;
}

export function importTimeKeys(shapes: Map<string, { shape: PyShape; text: string }>, resolve: Resolve): Set<string> {
  const scopes = new Map<string, Scope>();
  const defs = new Map<string, PyFunction>();
  const classes = new Map<string, PyFunction[]>();
  for (const [file, { shape, text }] of shapes) {
    scopes.set(file, moduleScope(file, text, resolve));
    for (const fn of shape.functions) {
      defs.set(`${file}:${fn.name}`, fn);
      if (fn.inClass !== undefined) classes.set(`${file}:${fn.inClass}`, [...(classes.get(`${file}:${fn.inClass}`) ?? []), fn]);
    }
  }
  const marked = new Set<string>();
  const queue: string[] = [];
  const mark = (key: string): void => {
    if (marked.has(key)) return;
    marked.add(key);
    queue.push(key);
  };
  const refer = (file: string, code: string): void => {
    const scope = scopes.get(file);
    for (const match of stripStrings(code).matchAll(/([A-Za-z_]\w*)(?:\s*\.\s*([A-Za-z_]\w*))?/g)) {
      const first = match[1] as string;
      const second = match[2];
      mark(`${file}:${first}`);
      const named = scope?.names.get(first);
      if (named !== undefined) mark(`${named[0]}:${named[1]}`);
      const module = scope?.modules.get(first);
      if (module !== undefined && second !== undefined) mark(`${module}:${second}`);
      for (const star of scope?.star ?? []) mark(`${star}:${first}`);
    }
  };
  for (const [file, { shape }] of shapes) refer(file, shape.importTime);
  while (queue.length > 0) {
    const key = queue.shift() as string;
    const file = key.slice(0, key.lastIndexOf(":"));
    const fn = defs.get(key);
    const entry = shapes.get(file);
    if (fn !== undefined && entry !== undefined) {
      const physical = entry.text.split("\n");
      refer(file, [...fn.header, ...fn.body].map((line) => physical[line] ?? "").join("\n"));
    }
    for (const method of classes.get(key) ?? []) mark(`${file}:${method.name}`);
  }
  return marked;
}

