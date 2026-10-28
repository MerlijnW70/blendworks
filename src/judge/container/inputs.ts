import { existsSync, readdirSync, realpathSync, statSync } from "node:fs";
import { extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { EntryError } from "./result.js";

export const ASSET_FORMATS = ["glb", "gltf", "fbx", "obj", "blend"] as const;

export type Layout = { root: string; work: string; spec: string; check: string; scratch: string; blendworks: string; blender: string };

export function layoutFrom(env: NodeJS.ProcessEnv = process.env): Layout {
  const root = env["BLENDWORKS_INPUT_ROOT"] ?? "/judge";
  return {
    root,
    work: join(root, "work"),
    spec: join(root, "spec"),
    check: join(root, "check"),
    scratch: env["BLENDWORKS_SCRATCH"] ?? "/tmp/blendworks",
    blendworks: env["BLENDWORKS_HOME"] ?? "/opt/blendworks",
    blender: env["BLENDER"] ?? "/opt/blender/blender",
  };
}

function inside(folder: string, path: string): boolean {
  const offset = relative(folder, path);
  return offset !== "" && offset !== ".." && !offset.startsWith(`..${sep}`) && !isAbsolute(offset);
}

export function inputPath(folder: string, given: string | undefined, label: string): string {
  if (given === undefined || given === "") throw new EntryError("error", `no ${label} was given; Solive sets it in the container`);
  const path = resolve(folder, given);
  if (!existsSync(path)) throw new EntryError("error", `the ${label} ${given} does not exist`);
  const real = realpathSync(path);
  const realFolder = existsSync(folder) ? realpathSync(folder) : folder;
  if (real !== realFolder && !inside(realFolder, real)) throw new EntryError("error", `the ${label} ${given} is outside the input folder ${folder}, so it is refused`);
  return real;
}

const FENCE = /^```json[^\n]*\n([\s\S]*?)\n```/gm;

export function assetSpecFrom(text: string): Record<string, unknown> {
  const whole = parsedObject(text);
  if (whole !== null) return whole;
  for (const match of text.matchAll(FENCE)) {
    const found = parsedObject(match[1] ?? "");
    if (found !== null) return found;
  }
  throw new EntryError("error", "the spec holds no asset spec: neither JSON nor a ```json block");
}

function parsedObject(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function isAsset(name: string): boolean {
  return (ASSET_FORMATS as readonly string[]).includes(extname(name).slice(1).toLowerCase());
}

export function mainAsset(artifact: string, folder: string): string {
  if (statSync(artifact).isFile()) {
    if (!isAsset(artifact)) throw new EntryError("fail", `the delivery ${relative(folder, artifact)} is not a ${ASSET_FORMATS.join(", ")} file`);
    return artifact;
  }
  const candidates = readdirSync(artifact, { withFileTypes: true }).filter((entry) => entry.isFile() && isAsset(entry.name));
  if (candidates.length !== 1) {
    throw new EntryError("fail", `the delivered folder must hold exactly one ${ASSET_FORMATS.join(", ")} file at its top, and holds ${candidates.length}`);
  }
  return inputPath(folder, join(artifact, candidates[0]!.name), "asset");
}
