const BINARY_MAGIC = "Kaydara FBX Binary  \u0000";
const HEADER_BYTES = 27;
const LARGE_RECORDS_FROM = 7500;
const MAX_DEPTH = 64;
const FILE_KEYS = new Set(["FileName", "RelativeFilename", "Filename", "Path"]);
const TEXTURE_NODES = new Set(["Texture", "Video"]);
const ARRAY_ELEMENT_BYTES: Record<string, number> = { f: 4, d: 8, l: 8, i: 4, b: 1 };

export type FbxTexture = { names: string[]; embedded: boolean; opened: string };

export class FbxError extends Error {}

type Property = string | number | bigint | boolean | Uint8Array | null;

type Node = { name: string; properties: Property[]; children: Node[] };

class Reader {
  private position = HEADER_BYTES;
  private readonly large: boolean;

  constructor(private readonly data: Buffer) {
    this.large = data.readUInt32LE(23) >= LARGE_RECORDS_FROM;
  }

  nodes(end: number, depth: number): Node[] {
    if (depth > MAX_DEPTH) throw new FbxError(`the FBX nests deeper than ${MAX_DEPTH} levels`);
    const found: Node[] = [];
    while (this.position < end) {
      const node = this.node(depth);
      if (node === null) break;
      found.push(node);
    }
    return found;
  }

  private offset(): number {
    const value = this.large ? Number(this.data.readBigUInt64LE(this.position)) : this.data.readUInt32LE(this.position);
    this.position += this.large ? 8 : 4;
    return value;
  }

  private node(depth: number): Node | null {
    const start = this.position;
    const end = this.offset();
    const count = this.offset();
    this.offset();
    const nameLength = this.data.readUInt8(this.position);
    this.position += 1;
    if (end === 0) return null;
    if (end <= start || end > this.data.length) throw new FbxError("the FBX has a record that ends outside the file");
    const name = this.data.toString("latin1", this.position, this.position + nameLength);
    this.position += nameLength;
    const properties: Property[] = [];
    for (let index = 0; index < count; index += 1) properties.push(this.property());
    const children = this.position < end ? this.nodes(end, depth + 1) : [];
    this.position = end;
    return { name, properties, children };
  }

  private take(length: number): Buffer {
    if (length < 0 || this.position + length > this.data.length) throw new FbxError("the FBX has a property that runs past the end of the file");
    const slice = this.data.subarray(this.position, this.position + length);
    this.position += length;
    return slice;
  }

  private property(): Property {
    const type = String.fromCharCode(this.take(1)[0] ?? 0);
    const scalar: Record<string, () => Property> = {
      Y: () => this.take(2).readInt16LE(0),
      C: () => this.take(1)[0] !== 0,
      I: () => this.take(4).readInt32LE(0),
      F: () => this.take(4).readFloatLE(0),
      D: () => this.take(8).readDoubleLE(0),
      L: () => this.take(8).readBigInt64LE(0),
    };
    const read = scalar[type];
    if (read !== undefined) return read();
    if (type === "S" || type === "R") {
      const bytes = this.take(this.take(4).readUInt32LE(0));
      return type === "S" ? bytes.toString("utf8") : new Uint8Array(bytes);
    }
    const element = ARRAY_ELEMENT_BYTES[type];
    if (element !== undefined) {
      const header = this.take(12);
      const compressed = header.readUInt32LE(4) === 1;
      this.take(compressed ? header.readUInt32LE(8) : header.readUInt32LE(0) * element);
      return null;
    }
    throw new FbxError(`the FBX has an unknown property type ${JSON.stringify(type)}`);
  }
}

function strings(node: Node): string[] {
  const found: string[] = [];
  for (const child of node.children) {
    if (FILE_KEYS.has(child.name)) for (const value of child.properties) if (typeof value === "string" && value !== "") found.push(value);
    if (child.name === "Properties70") {
      for (const entry of child.children) {
        const [key, ...rest] = entry.properties;
        const last = rest.at(-1);
        if (typeof key === "string" && FILE_KEYS.has(key) && typeof last === "string" && last !== "") found.push(last);
      }
    }
  }
  return found;
}

function firstString(node: Node, key: string): string {
  for (const child of node.children) {
    if (child.name !== key) continue;
    const value = child.properties[0];
    return typeof value === "string" ? value : "";
  }
  return "";
}

function nodeName(node: Node): string {
  const value = node.properties.find((property): property is string => typeof property === "string");
  if (value === undefined) return "";
  const split = value.indexOf("\u0000\u0001");
  return split === -1 ? value : value.slice(0, split);
}

export function openedPath(relative: string, fileName: string, videoName: string, name: string): string {
  return [relative, fileName, videoName].find((value) => value !== "") ?? name;
}

function embedded(node: Node): boolean {
  return node.children.some((child) => child.name === "Content" && child.properties.some((value) => value instanceof Uint8Array && value.length > 0));
}

function walk(nodes: Node[], found: FbxTexture[]): void {
  for (const node of nodes) {
    if (TEXTURE_NODES.has(node.name)) {
      const names = strings(node);
      const opened = openedPath(firstString(node, "RelativeFilename"), firstString(node, "FileName"), firstString(node, "Filename"), nodeName(node));
      found.push({ names, embedded: node.name === "Video" && embedded(node), opened });
    }
    walk(node.children, found);
  }
}

function asciiValue(block: string, key: string): string {
  return new RegExp(`^\\s*${key}:\\s*"([^"]*)"`, "m").exec(block)?.[1] ?? "";
}

function asciiTextures(text: string): FbxTexture[] {
  const found: FbxTexture[] = [];
  const blocks = text.split(/^\s*(?=(?:Texture|Video):)/m).filter((block) => /^\s*(?:Texture|Video):/.test(block));
  for (const block of blocks) {
    const names: string[] = [];
    for (const match of block.matchAll(/^\s*(?:FileName|RelativeFilename|Filename):\s*"([^"]*)"/gm)) if (match[1]) names.push(match[1]);
    for (const match of block.matchAll(/P:\s*"(?:Path|FileName|RelativeFilename)",[^\n]*"([^"]*)"\s*$/gm)) if (match[1]) names.push(match[1]);
    const name = /^\s*(?:Texture|Video):[^,\n]*,\s*"(?:\w+::)?([^"]*)"/.exec(block)?.[1] ?? "";
    const opened = openedPath(asciiValue(block, "RelativeFilename"), asciiValue(block, "FileName"), asciiValue(block, "Filename"), name);
    found.push({ names, embedded: /^\s*Video:/.test(block) && /^\s*Content:\s*,?\s*"[^"]/m.test(block), opened });
  }
  return found;
}

export function fbxTextures(data: Buffer): FbxTexture[] {
  if (data.length >= HEADER_BYTES && data.toString("latin1", 0, BINARY_MAGIC.length) === BINARY_MAGIC) {
    const found: FbxTexture[] = [];
    try {
      walk(new Reader(data).nodes(data.length, 0), found);
    } catch (error) {
      if (error instanceof FbxError) throw error;
      if (error instanceof RangeError) throw new FbxError("the FBX is cut off or damaged");
      throw error;
    }
    return found;
  }
  return asciiTextures(data.toString("utf8"));
}
