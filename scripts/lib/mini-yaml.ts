export type Yaml = string | Yaml[] | { [key: string]: Yaml };

type Line = { indent: number; text: string };

function significant(source: string): Line[] {
  const lines: Line[] = [];
  let block: number | null = null;
  for (const raw of source.split(/\r?\n/)) {
    const indent = raw.length - raw.trimStart().length;
    if (block !== null && (raw.trim() === "" || indent > block)) {
      if (raw.trim() !== "") lines.push({ indent, text: `\u0000${raw.trim()}` });
      continue;
    }
    block = null;
    const text = raw.trim();
    if (text === "" || text.startsWith("#")) continue;
    lines.push({ indent, text });
    if (/:\s*[|>][+-]?$/.test(text)) block = indent;
  }
  return lines;
}

function scalar(text: string): string {
  const quoted = /^(["'])(.*)\1$/.exec(text.trim());
  return quoted ? quoted[2]! : text.trim();
}

function parseBlock(lines: Line[], at: { i: number }, indent: number): Yaml {
  const first = lines[at.i]!;
  if (first.text.startsWith("- ") || first.text === "-") return parseSequence(lines, at, indent);
  return parseMap(lines, at, indent);
}

function parseSequence(lines: Line[], at: { i: number }, indent: number): Yaml {
  const items: Yaml[] = [];
  while (at.i < lines.length && lines[at.i]!.indent === indent && lines[at.i]!.text.startsWith("-")) {
    const line = lines[at.i]!;
    const rest = line.text.slice(1).trim();
    if (rest === "") {
      at.i += 1;
      items.push(parseBlock(lines, at, lines[at.i]!.indent));
    } else if (/^[\w.-]+:(\s|$)/.test(rest)) {
      lines[at.i] = { indent: indent + 2, text: rest };
      items.push(parseMap(lines, at, indent + 2));
    } else {
      at.i += 1;
      items.push(scalar(rest));
    }
  }
  return items;
}

function parseMap(lines: Line[], at: { i: number }, indent: number): Yaml {
  const map: { [key: string]: Yaml } = {};
  while (at.i < lines.length && lines[at.i]!.indent === indent && !lines[at.i]!.text.startsWith("\u0000")) {
    const found = /^([\w.\-"' ]+?):(?:\s+(.*))?$/.exec(lines[at.i]!.text);
    if (!found) throw new Error(`cannot parse line ${at.i + 1}: ${lines[at.i]!.text}`);
    const key = scalar(found[1]!);
    const value = (found[2] ?? "").trim();
    at.i += 1;
    if (/^[|>][+-]?$/.test(value)) {
      const body: string[] = [];
      while (at.i < lines.length && lines[at.i]!.text.startsWith("\u0000")) body.push(lines[at.i++]!.text.slice(1));
      map[key] = body.join("\n");
    } else if (value === "") {
      const next = lines[at.i];
      map[key] = next && (next.indent > indent || (next.indent === indent && next.text.startsWith("-"))) ? parseBlock(lines, at, next.indent) : "";
    } else map[key] = scalar(value.replace(/\s+#.*$/, ""));
  }
  return map;
}

export function parseYaml(source: string): Yaml {
  const lines = significant(source);
  if (lines.length === 0) return {};
  const at = { i: 0 };
  const result = parseBlock(lines, at, lines[0]!.indent);
  if (at.i < lines.length) throw new Error(`unparsed content at line ${at.i + 1}: ${lines[at.i]!.text}`);
  return result;
}
