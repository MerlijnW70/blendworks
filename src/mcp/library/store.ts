import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, mkdtemp, readdir, readFile, rename, rm, rmdir, stat, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import { z } from "zod";
import type { Workspace } from "../workspace.js";
import { ASSET_ID, ASSET_TYPES, type AssetType, checkAssetId, checkRelativePath, FORMAT, LIBRARY_FOLDER, LICENSE, LICENSE_URL, LibraryError, MD5, RESOLUTION } from "./common.js";
import type { Asset } from "./schemas.js";
import type { Plan } from "./plan.js";

export const LICENSE_FILE = "LICENSE.json";
const TMP_FOLDER = ".tmp";
const STALE_TMP_MS = 6 * 60 * 60 * 1000;

const relativePath = z.string().min(1).max(400).refine((path) => {
  try {
    checkRelativePath(path);
    return true;
  } catch {
    return false;
  }
});

export const licenseSchema = z.object({
  asset: z.string().regex(ASSET_ID),
  name: z.string().min(1),
  type: z.enum(ASSET_TYPES),
  source: z.string().url(),
  license: z.literal(LICENSE),
  license_url: z.literal(LICENSE_URL),
  authors: z.record(z.string(), z.string()),
  resolution: z.string().regex(RESOLUTION),
  format: z.string().regex(FORMAT),
  main: relativePath.optional(),
  maps: z.record(z.string(), relativePath).optional(),
  files: z.array(z.object({ path: relativePath, url: z.string().url(), bytes: z.number().int().positive(), md5: z.string().regex(MD5) })).min(1),
  downloaded_at: z.string().min(1),
});
export type LicenseRecord = z.infer<typeof licenseSchema>;

export function assetFolderPath(type: AssetType, id: string): string {
  return `${LIBRARY_FOLDER}/${type}/${checkAssetId(id)}`;
}

export function assetFolder(workspace: Workspace, type: AssetType, id: string): string {
  return workspace.resolve(assetFolderPath(type, id));
}

function inside(folder: string, path: string): string {
  const target = resolve(folder, ...path.split("/"));
  const rel = relative(folder, target);
  if (rel === "" || rel.startsWith(`..${sep}`) || rel === ".." || resolve(folder, rel) !== target) {
    throw new LibraryError("refused", `${path} is outside the asset folder`);
  }
  return target;
}

export async function readLocal(workspace: Workspace, type: AssetType, id: string): Promise<LicenseRecord | undefined> {
  const folder = assetFolder(workspace, type, id);
  let text: string;
  try {
    text = await readFile(join(folder, LICENSE_FILE), "utf8");
  } catch {
    return undefined;
  }
  let parsed;
  try {
    parsed = licenseSchema.safeParse(JSON.parse(text));
  } catch {
    throw new LibraryError("invalid", `${assetFolderPath(type, id)}/${LICENSE_FILE} is not valid JSON; download the asset again`);
  }
  if (!parsed.success || parsed.data.asset !== id || parsed.data.type !== type) {
    throw new LibraryError("invalid", `${assetFolderPath(type, id)}/${LICENSE_FILE} is not a library record for ${id}; download the asset again`);
  }
  return parsed.data;
}

function md5Of(path: string): Promise<string> {
  return new Promise((done, fail) => {
    const hash = createHash("md5");
    createReadStream(path)
      .on("data", (chunk) => hash.update(chunk))
      .on("error", fail)
      .on("end", () => done(hash.digest("hex")));
  });
}

export async function verifyLocal(workspace: Workspace, record: LicenseRecord): Promise<string | undefined> {
  const folder = assetFolder(workspace, record.type, record.asset);
  for (const file of record.files) {
    const path = inside(folder, file.path);
    const info = await stat(path).catch(() => undefined);
    if (info === undefined || !info.isFile()) return `${file.path} is missing`;
    if (info.size !== file.bytes) return `${file.path} is ${info.size} bytes, not ${file.bytes}`;
    if ((await md5Of(path)) !== file.md5) return `${file.path} does not match its md5`;
  }
  return undefined;
}

export async function cleanStaleTemporary(workspace: Workspace, now: number): Promise<void> {
  const folder = workspace.resolve(`${LIBRARY_FOLDER}/${TMP_FOLDER}`);
  const entries = await readdir(folder).catch(() => [] as string[]);
  for (const entry of entries) {
    const path = join(folder, entry);
    const info = await stat(path).catch(() => undefined);
    if (info !== undefined && now - info.mtimeMs > STALE_TMP_MS) await rm(path, { recursive: true, force: true });
  }
}

export interface Fetcher {
  download(file: { url: string; size: number; md5: string }, target: string, budget: { left: number }, signal?: AbortSignal): Promise<void>;
}

function gltfReferences(text: string): string[] {
  let document: unknown;
  try {
    document = JSON.parse(text);
  } catch {
    throw new LibraryError("invalid", "the downloaded .gltf file is not JSON");
  }
  if (typeof document !== "object" || document === null) throw new LibraryError("invalid", "the downloaded .gltf file is not a glTF document");
  const references: string[] = [];
  for (const key of ["buffers", "images"]) {
    const entries = (document as Record<string, unknown>)[key];
    if (!Array.isArray(entries)) continue;
    for (const entry of entries) {
      const uri = typeof entry === "object" && entry !== null ? (entry as Record<string, unknown>)["uri"] : undefined;
      if (typeof uri === "string" && !uri.startsWith("data:")) references.push(uri);
    }
  }
  return references;
}

async function checkGltf(folder: string, plan: Plan): Promise<void> {
  if (plan.type !== "model" || plan.main === undefined) return;
  const present = new Set(plan.files.map((file) => file.path));
  for (const uri of gltfReferences(await readFile(inside(folder, plan.main), "utf8"))) {
    let path: string;
    try {
      path = decodeURIComponent(uri);
    } catch {
      path = uri;
    }
    if (!present.has(path)) throw new LibraryError("refused", `the glTF refers to ${uri.slice(0, 200)}, which is not one of the files Poly Haven lists for it`);
  }
}

async function pool<T>(items: T[], limit: number, run: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  let failure: unknown;
  const worker = async () => {
    while (failure === undefined && next < items.length) {
      const item = items[next] as T;
      next += 1;
      try {
        await run(item);
      } catch (error) {
        failure ??= error;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  if (failure !== undefined) throw failure;
}

export interface StoreRequest {
  workspace: Workspace;
  fetcher: Fetcher;
  id: string;
  asset: Asset;
  plan: Plan;
  maxBytes: number;
  now: Date;
  concurrency: number;
  signal?: AbortSignal | undefined;
}

export async function storeAsset(request: StoreRequest): Promise<LicenseRecord> {
  const { workspace, plan, id } = request;
  if (plan.files.some((file) => file.path.toLowerCase() === LICENSE_FILE.toLowerCase())) {
    throw new LibraryError("refused", `Poly Haven lists a file named ${LICENSE_FILE}, which the library keeps for its own record`);
  }
  const final = assetFolder(workspace, plan.type, id);
  const tmpRoot = workspace.resolve(`${LIBRARY_FOLDER}/${TMP_FOLDER}`);
  await mkdir(tmpRoot, { recursive: true });
  const temporary = await mkdtemp(join(tmpRoot, `${plan.type}-${id}-`));
  const previous = `${temporary}-previous`;
  try {
    const budget = { left: request.maxBytes };
    await pool(plan.files, request.concurrency, async (file) => {
      const target = inside(temporary, file.path);
      await mkdir(dirname(target), { recursive: true });
      await request.fetcher.download(file, target, budget, request.signal);
    });
    await checkGltf(temporary, plan);
    const record: LicenseRecord = {
      asset: id,
      name: request.asset.name,
      type: plan.type,
      source: `https://polyhaven.com/a/${id}`,
      license: LICENSE,
      license_url: LICENSE_URL,
      authors: request.asset.authors,
      resolution: plan.resolution,
      format: plan.format,
      ...(plan.main === undefined ? {} : { main: plan.main }),
      ...(plan.maps === undefined ? {} : { maps: plan.maps }),
      files: plan.files.map((file) => ({ path: file.path, url: file.url, bytes: file.size, md5: file.md5 })),
      downloaded_at: request.now.toISOString(),
    };
    await writeFile(join(temporary, LICENSE_FILE), `${JSON.stringify(record, null, 2)}\n`);
    await mkdir(dirname(final), { recursive: true });
    workspace.resolve(assetFolderPath(plan.type, id));
    const hadPrevious = await stat(final).then(() => true, () => false);
    if (hadPrevious) await rename(final, previous);
    try {
      await rename(temporary, final);
    } catch (error) {
      if (hadPrevious) await rename(previous, final).catch(() => undefined);
      throw new LibraryError("failed", `could not move the download into ${assetFolderPath(plan.type, id)}: ${error instanceof Error ? error.message : String(error)}`);
    }
    return record;
  } finally {
    await rm(temporary, { recursive: true, force: true });
    await rm(previous, { recursive: true, force: true });
    await rmdir(tmpRoot).catch(() => undefined);
  }
}
