import type { CallToolResult, Tool } from "@modelcontextprotocol/sdk/types.js";
import type { z } from "zod";
import { BridgeError } from "../protocol.js";
import type { Content } from "../results.js";
import { type Workspace, WorkspaceError } from "../workspace.js";
import { type Applied, applyAsset, type BridgeAccess } from "./apply.js";
import { PolyHavenClient } from "./client.js";
import { ASSET_TYPES, type AssetType, LIBRARY_FOLDER, LibraryError, megabytes } from "./common.js";
import type { FetchLike } from "./http.js";
import { planDownload } from "./plan.js";
import { filterListing, resolutionsOf, summary, typeOf } from "./search.js";
import { assetFolderPath, cleanStaleTemporary, type LicenseRecord, readLocal, storeAsset, verifyLocal } from "./store.js";
import { applyArgs, describeArgsError, downloadArgs, LIBRARY_PREFIX, LIBRARY_TOOLS, previewArgs, searchArgs } from "./tools.js";

export { LIBRARY_PREFIX, LIBRARY_TOOLS } from "./tools.js";
export type { BridgeAccess } from "./apply.js";

export const DEFAULT_MAX_BYTES = 300_000_000;
export const THUMBNAIL_MAX_BYTES = 1024 * 1024;
const RESOLUTION_LOOKUPS = 4;
const DOWNLOAD_CONCURRENCY = 3;

export interface LibraryOptions {
  workspace: Workspace;
  fetch?: FetchLike;
  maxBytes?: number;
  cacheTtlMs?: number;
  timeoutMs?: number;
  retries?: number;
  backoffMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

const OFFLINE_HINT = "Assets already downloaded into library/ still work with library_apply.";

function text(value: unknown): Content {
  return { type: "text", text: typeof value === "string" ? value : JSON.stringify(value) };
}

function failure(message: string): CallToolResult {
  return { content: [text(message)], isError: true };
}

function explain(error: unknown, tool: string): string {
  if (error instanceof LibraryError) {
    if (error.code === "offline") {
      const what = tool === "library_search" ? "Search needs the network" : `${tool} needs the network`;
      return `offline: Poly Haven is unreachable, ${error.message}. ${what}. ${OFFLINE_HINT}`;
    }
    return `${error.code}: ${error.message}`;
  }
  if (error instanceof WorkspaceError) return `refused: ${error.message}`;
  if (error instanceof BridgeError) return `${error.code}: ${error.message}`;
  return `failed: ${error instanceof Error ? error.message : String(error)}`;
}

function reasonOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function parse<S extends z.ZodType>(schema: S, args: unknown): z.infer<S> {
  const parsed = schema.safeParse(args ?? {});
  if (!parsed.success) throw new LibraryError("refused", `bad arguments: ${describeArgsError(parsed.error)}`);
  return parsed.data;
}

async function inBatches<T, R>(items: T[], size: number, run: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = [];
  for (let start = 0; start < items.length; start += size) out.push(...(await Promise.all(items.slice(start, start + size).map(run))));
  return out;
}

function sameMaps(record: LicenseRecord, maps: string[] | undefined): boolean {
  if (maps === undefined) return true;
  const have = Object.keys(record.maps ?? {}).sort();
  const want = [...new Set(maps)].sort();
  return have.length === want.length && have.every((map, index) => map === want[index]);
}

function downloadResult(record: LicenseRecord, alreadyPresent: boolean): Record<string, unknown> {
  const total = record.files.reduce((sum, file) => sum + file.bytes, 0);
  return {
    id: record.asset,
    type: record.type,
    folder: assetFolderPath(record.type, record.asset),
    resolution: record.resolution,
    format: record.format,
    ...(record.main === undefined ? {} : { main: `${assetFolderPath(record.type, record.asset)}/${record.main}` }),
    ...(record.maps === undefined ? {} : { maps: record.maps }),
    files: record.files.map((file) => ({ path: file.path, bytes: file.bytes })),
    total: megabytes(total),
    license: record.license,
    authors: Object.keys(record.authors),
    already_present: alreadyPresent,
    next: "library_apply",
  };
}

export class Library {
  readonly tools: Tool[] = LIBRARY_TOOLS;
  private readonly client: PolyHavenClient;
  private readonly maxBytes: number;
  private readonly now: () => number;
  private readonly busy = new Map<string, Promise<unknown>>();

  constructor(private readonly options: LibraryOptions) {
    this.maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES;
    this.now = options.now ?? Date.now;
    const optional = {
      ...(options.fetch === undefined ? {} : { fetch: options.fetch }),
      ...(options.cacheTtlMs === undefined ? {} : { cacheTtlMs: options.cacheTtlMs }),
      ...(options.timeoutMs === undefined ? {} : { timeoutMs: options.timeoutMs }),
      ...(options.retries === undefined ? {} : { retries: options.retries }),
      ...(options.backoffMs === undefined ? {} : { backoffMs: options.backoffMs }),
      ...(options.sleep === undefined ? {} : { sleep: options.sleep }),
    };
    this.client = new PolyHavenClient({ cacheDir: () => options.workspace.resolve(`${LIBRARY_FOLDER}/.cache`), now: this.now, ...optional });
  }

  has(name: string): boolean {
    return this.tools.some((tool) => tool.name === name);
  }

  async call(name: string, args: unknown, bridge: BridgeAccess, signal?: AbortSignal): Promise<CallToolResult> {
    try {
      if (signal?.aborted) throw new LibraryError("cancelled", `${name} was cancelled before it started`);
      if (name === "library_search") return { content: [text(await this.search(parse(searchArgs, args), signal))] };
      if (name === "library_preview") return await this.preview(parse(previewArgs, args), signal);
      if (name === "library_download") return { content: [text(await this.download(parse(downloadArgs, args), signal))] };
      if (name === "library_apply") {
        const cancellable: BridgeAccess = { commands: bridge.commands, request: (cmd, requestArgs, options) => bridge.request(cmd, requestArgs, { ...(signal === undefined ? {} : { signal }), ...options }) };
        return this.applied(await applyAsset(cancellable, this.options.workspace, parse(applyArgs, args)));
      }
      return failure(`Unknown tool ${name}; the library tools start with ${LIBRARY_PREFIX}.`);
    } catch (error) {
      return failure(explain(error, name));
    }
  }

  private async checkCategory(types: readonly AssetType[], category: string, signal?: AbortSignal): Promise<void> {
    const known = new Set<string>();
    for (const type of types) for (const name of Object.keys(await this.client.categories(type, signal))) known.add(name);
    if ([...known].some((name) => name.toLowerCase() === category.toLowerCase())) return;
    const sample = [...known].filter((name) => name !== "all").slice(0, 40);
    throw new LibraryError("refused", `"${category}" is not a Poly Haven category for ${types.join(", ")}; known categories include ${sample.join(", ")}`);
  }

  private async search(args: z.infer<typeof searchArgs>, signal?: AbortSignal): Promise<Record<string, unknown>> {
    const types = args.type === undefined ? ASSET_TYPES : [args.type];
    if (args.category !== undefined) await this.checkCategory(types, args.category, signal);
    const listing = Object.assign({}, ...(await Promise.all(types.map((type) => this.client.assets(type, signal)))));
    const page = filterListing(listing, {
      ...(args.query === undefined ? {} : { text: args.query }),
      ...(args.category === undefined ? {} : { categories: [args.category] }),
      ...(args.tags === undefined ? {} : { tags: args.tags }),
      page: args.page,
      perPage: args.per_page,
    });
    const settled = await inBatches(page.matches, RESOLUTION_LOOKUPS, async ({ id, asset }) => {
      try {
        const type = typeOf(asset);
        return { id, name: asset.name, summary: summary(id, asset, resolutionsOf(type, await this.client.files(id, type, signal))) };
      } catch (error) {
        if (signal?.aborted) throw error;
        return { id, name: asset.name, error };
      }
    });
    const results = settled.flatMap((entry) => ("summary" in entry ? [entry.summary] : []));
    const failed = settled.flatMap((entry) => ("error" in entry ? [entry] : []));
    const first = failed[0];
    if (results.length === 0 && first !== undefined && first.error instanceof LibraryError && failed.every((entry) => entry.error instanceof LibraryError && entry.error.code === "offline")) throw first.error;
    const unavailable = failed.map((entry) => ({ id: entry.id, name: entry.name, reason: reasonOf(entry.error) }));
    return { total: page.total, page: page.page, pages: page.pages, per_page: args.per_page, results, ...(unavailable.length === 0 ? {} : { unavailable }) };
  }

  private async preview(args: z.infer<typeof previewArgs>, signal?: AbortSignal): Promise<CallToolResult> {
    const asset = await this.client.info(args.id, signal);
    const thumbnail = await this.client.thumbnail(asset, args.size, THUMBNAIL_MAX_BYTES, signal);
    return {
      content: [
        text(`${asset.name} (${typeOf(asset)}, ${args.id}): thumbnail ${thumbnail.width}x${thumbnail.height} px, ${thumbnail.data.length} bytes.`),
        { type: "image", data: thumbnail.data.toString("base64"), mimeType: "image/png" },
      ],
    };
  }

  private async localCopy(args: z.infer<typeof downloadArgs>): Promise<LicenseRecord | undefined> {
    for (const type of ASSET_TYPES) {
      const record = await readLocal(this.options.workspace, type, args.id).catch(() => undefined);
      if (record === undefined || record.resolution !== args.resolution || !sameMaps(record, args.maps)) continue;
      if (args.format !== undefined && record.format !== args.format) continue;
      if ((await verifyLocal(this.options.workspace, record)) === undefined) return record;
    }
    return undefined;
  }

  private async download(args: z.infer<typeof downloadArgs>, signal?: AbortSignal): Promise<Record<string, unknown>> {
    const key = args.id.toLowerCase();
    while (this.busy.has(key)) await this.busy.get(key)?.catch(() => undefined);
    const work = this.downloadNow(args, signal);
    this.busy.set(key, work);
    try {
      return await work;
    } finally {
      this.busy.delete(key);
    }
  }

  private async downloadNow(args: z.infer<typeof downloadArgs>, signal?: AbortSignal): Promise<Record<string, unknown>> {
    const local = await this.localCopy(args);
    if (local !== undefined) return downloadResult(local, true);
    const asset = await this.client.info(args.id, signal);
    const type = typeOf(asset);
    const plan = planDownload(type, await this.client.files(args.id, type, signal), { resolution: args.resolution, format: args.format, maps: args.maps }, this.maxBytes);
    await cleanStaleTemporary(this.options.workspace, this.now());
    const record = await storeAsset({
      workspace: this.options.workspace,
      fetcher: this.client,
      id: args.id,
      asset,
      plan,
      maxBytes: this.maxBytes,
      now: new Date(this.now()),
      concurrency: DOWNLOAD_CONCURRENCY,
      signal,
    });
    return downloadResult(record, false);
  }

  private applied(applied: Applied): CallToolResult {
    const record = applied.record;
    const result = {
      id: record.asset,
      type: record.type,
      folder: assetFolderPath(record.type, record.asset),
      steps: applied.steps.map((step) => ({ command: `blender_${step.command}`, result: step.result })),
      ...(applied.notWired === undefined ? {} : { maps_not_wired: applied.notWired }),
      license: `${record.license}, by ${Object.keys(record.authors).join(", ")}`,
    };
    return { content: [...applied.notices.map(text), text(result)] };
  }
}

export function libraryOptionsFromEnv(env: NodeJS.ProcessEnv): Pick<LibraryOptions, "maxBytes"> {
  const raw = env["BLENDWORKS_LIBRARY_MAX_MB"];
  if (raw === undefined || raw.trim() === "") return {};
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`BLENDWORKS_LIBRARY_MAX_MB must be a positive number of megabytes, not "${raw}"`);
  return { maxBytes: Math.round(value * 1_000_000) };
}
