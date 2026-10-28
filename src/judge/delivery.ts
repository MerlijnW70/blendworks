import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, realpathSync, statSync } from "node:fs";
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { BlendScanError, blendReferences } from "./blend-refs.js";
import { FbxError, fbxTextures } from "./fbx.js";
import { checkReference, type ReferenceStyle } from "./path-policy.js";
import { quoted } from "./untrusted.js";

export const MAX_DELIVERED_FILES = 1024;
const GLB_MAGIC = "glTF";
const GLB_JSON_CHUNK = 0x4e4f534a;
const MTL_MAP = /^(map_\w+|bump|disp|decal|refl|norm)\s+(.+)$/i;
const MTL_OPTION_ARGUMENTS: Record<string, number> = { o: 3, s: 3, t: 3, mm: 2, bm: 1, boost: 1, texres: 1, blendu: 1, blendv: 1, cc: 1, clamp: 1, imfchan: 1, type: 1 };

const OUTSIDE = "the file is outside the asset folder";
const NOT_A_FILE = "the reference is not a file";
const MISSING = "the file is not in the asset folder";

export type DeliveredFile = { path: string; bytes: number; sha256: string };

export type Delivery = {
  folder: string;
  main: string;
  files: DeliveredFile[];
  bytes: number;
  sha256: string;
  references: { files: number; unresolved: string[] };
};

export class DeliveryError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

type Opened = { raw: string; style: ReferenceStyle; within?: string };

type Reference = { label: string; candidates: string[]; opened: Opened[]; optional?: boolean };

type Found = { relative: string; real: string };

function digest(data: Buffer | string): string {
  return createHash("sha256").update(data).digest("hex");
}

function gltfJson(path: string, format: string): Record<string, unknown> | null {
  const data = readFileSync(path);
  let text: string;
  if (format === "glb") {
    if (data.length < 20 || data.toString("latin1", 0, 4) !== GLB_MAGIC || data.readUInt32LE(16) !== GLB_JSON_CHUNK) return null;
    text = data.toString("utf8", 20, Math.min(data.length, 20 + data.readUInt32LE(12)));
  } else text = data.toString("utf8");
  try {
    const document: unknown = JSON.parse(text);
    return document !== null && typeof document === "object" ? (document as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function gltfReferences(path: string, format: string): Reference[] {
  const document = gltfJson(path, format);
  if (document === null) return [];
  const references: Reference[] = [];
  for (const key of ["buffers", "images"]) {
    const entries = document[key];
    if (!Array.isArray(entries)) continue;
    entries.forEach((entry: unknown, index) => {
      const uri = entry !== null && typeof entry === "object" ? (entry as { uri?: unknown }).uri : undefined;
      if (typeof uri !== "string" || uri.startsWith("data:")) return;
      let decoded = uri;
      try {
        decoded = decodeURIComponent(uri);
      } catch {
        decoded = uri;
      }
      references.push({ label: `${key}[${index}] ${quoted(uri, 200)}`, candidates: [decoded], opened: [{ raw: uri, style: "uri" }] });
    });
  }
  return references;
}

function mtlFileName(rest: string): string {
  const tokens = rest.trim().split(/\s+/);
  let index = 0;
  while (index < tokens.length - 1 && tokens[index]?.startsWith("-")) {
    const option = tokens[index]!.slice(1);
    index += 1;
    const most = MTL_OPTION_ARGUMENTS[option] ?? 0;
    for (let taken = 0; taken < most && index < tokens.length - 1; taken += 1) {
      if (most === 3 && taken > 0 && !/^[-+]?(\d|\.\d)/.test(tokens[index]!)) break;
      index += 1;
    }
  }
  return tokens.slice(index).join(" ");
}

function objReferences(path: string, folder: string): Reference[] {
  const lines = readFileSync(path, "utf8").split(/\r?\n/);
  const libraries = lines.filter((line) => /^mtllib\s/.test(line)).map((line) => line.slice(6).trim()).filter((name) => name !== "");
  const references: Reference[] = libraries.map((name) => ({ label: `mtllib ${quoted(name, 200)}`, candidates: [name], opened: [{ raw: name, style: "path" }] }));
  if (libraries.length === 0) references.push({ label: "implicit material library", candidates: [`${basename(path, extname(path))}.mtl`], opened: [], optional: true });
  for (const library of [...references]) {
    const found = locate(folder, library.candidates);
    if ("reason" in found) continue;
    for (const line of readFileSync(found.real, "utf8").split(/\r?\n/)) {
      const match = MTL_MAP.exec(line.trim());
      if (match === null) continue;
      const name = mtlFileName(match[2] ?? "");
      if (name !== "") {
        const within = dirname(found.relative) === "." ? undefined : dirname(found.relative);
        const label = `${match[1]} ${quoted(name, 200)} in ${quoted(found.relative, 200)}`;
        references.push({ label, candidates: [name, basename(name.replaceAll("\\", "/"))], opened: [{ raw: name, style: "path", ...(within === undefined ? {} : { within }) }] });
      }
    }
  }
  return references;
}

function fbxReferences(path: string): Reference[] {
  let textures;
  try {
    textures = fbxTextures(readFileSync(path));
  } catch (error) {
    if (error instanceof FbxError) throw new DeliveryError("corrupt", error.message);
    throw error;
  }
  const embedded = new Set(textures.filter((texture) => texture.embedded).flatMap((texture) => texture.names.map((name) => basename(name.replaceAll("\\", "/")))));
  const references: Reference[] = [];
  const seen = new Set<string>();
  for (const texture of textures) {
    references.push({ label: `texture ${quoted(texture.opened, 200)}`, candidates: [], opened: [{ raw: texture.opened, style: "path" }], optional: true });
    if (texture.embedded || texture.names.length === 0) continue;
    const names = texture.names.map((name) => name.replaceAll("\\", "/"));
    if (names.some((name) => embedded.has(basename(name)))) continue;
    const key = names.join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    references.push({ label: `texture ${quoted(basename(names[0]!), 200)}`, candidates: [...names, ...names.map((name) => basename(name))], opened: [] });
  }
  return references;
}

function blendFileReferences(path: string): Reference[] {
  let found;
  try {
    found = blendReferences(readFileSync(path));
  } catch (error) {
    if (error instanceof BlendScanError) throw new DeliveryError("corrupt", error.message);
    throw error;
  }
  return found.map((entry) => ({ label: `${entry.kind} ${quoted(entry.name)} ${quoted(entry.path, 200)}`, candidates: [], opened: [{ raw: entry.path, style: "blend" }], optional: true }));
}

export function refusal(opened: Opened): string | null {
  const verdict = checkReference(opened.raw, opened.style);
  if (verdict.ok || verdict.code !== "escape" || opened.within === undefined) return verdict.ok ? null : verdict.reason;
  const inside = checkReference(`${opened.within}/${opened.raw}`, opened.style);
  return inside.ok ? null : inside.reason;
}

function locate(folder: string, candidates: string[]): Found | { reason: string } {
  const reasons = new Set<string>();
  for (const candidate of candidates) {
    const verdict = checkReference(candidate, "path");
    if (!verdict.ok) {
      reasons.add(verdict.code === "escape" ? OUTSIDE : MISSING);
      continue;
    }
    const target = resolve(folder, ...verdict.path.split("/"));
    if (!existsSync(target)) {
      reasons.add(MISSING);
      continue;
    }
    const real = realpathSync(target);
    const inside = relative(folder, real);
    if (inside === "" || inside === ".." || inside.startsWith(`..${sep}`) || isAbsolute(inside)) {
      reasons.add(OUTSIDE);
      continue;
    }
    if (!statSync(real).isFile()) {
      reasons.add(NOT_A_FILE);
      continue;
    }
    return { relative: inside.split(sep).join("/"), real };
  }
  return { reason: [OUTSIDE, NOT_A_FILE, MISSING].find((reason) => reasons.has(reason)) ?? MISSING };
}

function references(path: string, format: string, folder: string): Reference[] {
  if (format === "glb" || format === "gltf") return gltfReferences(path, format);
  if (format === "obj") return objReferences(path, folder);
  if (format === "fbx") return fbxReferences(path);
  if (format === "blend") return blendFileReferences(path);
  return [];
}

export function copyDelivery(assetPath: string, format: string, into: string, maxBytes: number): Delivery {
  const real = realpathSync(assetPath);
  const folder = dirname(real);
  const chosen = new Map<string, string>([[basename(real), real]]);
  const unresolved: string[] = [];
  const listed = references(real, format, folder);
  const refused = [...new Set(listed.flatMap((reference) => reference.opened.flatMap((opened) => {
    const reason = refusal(opened);
    return reason === null ? [] : [`${reference.label}: ${reason}`];
  })))].sort();
  if (refused.length > 0) {
    throw new DeliveryError("external_reference", `the delivery refers to files the judge never opens, so it is refused before Blender starts: ${refused.slice(0, 10).join("; ")}${refused.length > 10 ? `; and ${refused.length - 10} more` : ""}`);
  }
  for (const reference of listed) {
    if (reference.candidates.length === 0) continue;
    const found = locate(folder, reference.candidates);
    if ("reason" in found) {
      const entry = `${reference.label}: ${found.reason}`;
      if (reference.optional !== true && !unresolved.includes(entry)) unresolved.push(entry);
      continue;
    }
    chosen.set(found.relative, found.real);
    if (chosen.size > MAX_DELIVERED_FILES) throw new DeliveryError("too_many_files", `the delivery refers to more than ${MAX_DELIVERED_FILES} files`);
  }
  const total = [...chosen.values()].reduce((sum, path) => sum + statSync(path).size, 0);
  if (total > maxBytes) throw new DeliveryError("too_large", `the delivery is ${total} bytes with the files it refers to, over the judge's cap of ${maxBytes}`);
  const target = join(into, "delivery");
  const files: DeliveredFile[] = [];
  for (const [relativePath, source] of [...chosen.entries()].sort(([first], [second]) => (first < second ? -1 : first > second ? 1 : 0))) {
    const destination = join(target, ...relativePath.split("/"));
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(source, destination);
    const data = readFileSync(destination);
    files.push({ path: relativePath, bytes: data.length, sha256: digest(data) });
  }
  const manifest = files.map((file) => `${file.sha256}  ${file.path}\n`).join("");
  return {
    folder: target,
    main: join(target, basename(real)),
    files,
    bytes: files.reduce((sum, file) => sum + file.bytes, 0),
    sha256: digest(manifest),
    references: { files: listed.filter((reference) => reference.candidates.length > 0).length, unresolved: unresolved.sort() },
  };
}
