import { createHash } from "node:crypto";
import { open } from "node:fs/promises";
import type { z } from "zod";
import { DiskCache } from "./cache.js";
import { API_BASE, API_TYPE_NAMES, type AssetType, checkAssetId, LibraryError } from "./common.js";
import { type FetchLike, Http, readCapped } from "./http.js";
import {
  type Asset,
  assetSchema,
  categoriesSchema,
  describeIssues,
  hdriFilesSchema,
  type Listing,
  listingSchema,
  type Resolutions,
  type SetFiles,
  setFilesSchema,
} from "./schemas.js";

export const USER_AGENT = "Blendworks/0.0 (Blender tools for AI agents; Poly Haven asset library)";
export const MAX_JSON_BYTES = 16 * 1024 * 1024;
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

export interface ClientOptions {
  fetch?: FetchLike;
  cacheDir: string | (() => string);
  cacheTtlMs?: number;
  timeoutMs?: number;
  retries?: number;
  backoffMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  userAgent?: string;
}

export interface Thumbnail {
  data: Buffer;
  width: number;
  height: number;
}

export interface ExpectedFile {
  url: string;
  size: number;
  md5: string;
}

function diskError(target: string, error: unknown): LibraryError {
  return new LibraryError("failed", `could not write ${target}: ${error instanceof Error ? error.message : String(error)}`);
}

export const DEFAULT_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export class PolyHavenClient {
  private readonly http: Http;
  private readonly cache: DiskCache;

  constructor(options: ClientOptions) {
    this.http = new Http({
      fetch: options.fetch ?? ((url, init) => fetch(url, init)),
      userAgent: options.userAgent ?? USER_AGENT,
      timeoutMs: options.timeoutMs ?? 20_000,
      retries: options.retries ?? 2,
      backoffMs: options.backoffMs ?? 500,
      sleep: options.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms))),
    });
    const cacheDir = options.cacheDir;
    this.cache = new DiskCache(typeof cacheDir === "string" ? () => cacheDir : cacheDir, options.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS, options.now ?? Date.now);
  }

  async assets(type: AssetType, signal?: AbortSignal): Promise<Listing> {
    const name = API_TYPE_NAMES[type];
    return this.json(`assets-${name}`, `${API_BASE}/assets?t=${name}`, listingSchema, signal);
  }

  async categories(type: AssetType, signal?: AbortSignal): Promise<Record<string, number>> {
    const name = API_TYPE_NAMES[type];
    return this.json(`categories-${name}`, `${API_BASE}/categories/${name}`, categoriesSchema, signal);
  }

  async info(id: string, signal?: AbortSignal): Promise<Asset> {
    checkAssetId(id);
    return this.json(`info-${id}`, `${API_BASE}/info/${id}`, assetSchema, signal);
  }

  async files(id: string, type: AssetType, signal?: AbortSignal): Promise<SetFiles | { hdri: Resolutions }> {
    checkAssetId(id);
    if (type === "hdri") return this.json(`files-${id}`, `${API_BASE}/files/${id}`, hdriFilesSchema, signal);
    return this.json(`files-${id}`, `${API_BASE}/files/${id}`, setFilesSchema, signal);
  }

  async thumbnail(asset: Asset, size: number, maxBytes: number, signal?: AbortSignal): Promise<Thumbnail> {
    const url = new URL(asset.thumbnail_url);
    url.search = new URLSearchParams({ width: String(size), height: String(size), format: "png" }).toString();
    return this.http.get(url.href, "image/png", async (attempt) => {
      const data = await readCapped(attempt, maxBytes, "the thumbnail");
      if (data.length < 24 || !data.subarray(0, 8).equals(PNG_SIGNATURE) || data.toString("latin1", 12, 16) !== "IHDR") {
        throw new LibraryError("invalid", "the thumbnail Poly Haven sent is not a PNG image");
      }
      return { data, width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
    }, signal);
  }

  async download(expected: ExpectedFile, target: string, budget: { left: number }, signal?: AbortSignal): Promise<void> {
    await this.http.get(expected.url, "*/*", async (attempt) => {
      const declared = Number(attempt.response.headers.get("content-length") ?? "NaN");
      if (Number.isFinite(declared) && declared !== expected.size) {
        throw new LibraryError("refused", `${expected.url} is ${declared} bytes, but Poly Haven publishes ${expected.size}`);
      }
      if (expected.size > budget.left) throw new LibraryError("refused", `${expected.url} would go over the download size cap`);
      const hash = createHash("md5");
      const handle = await open(target, "w").catch((error: unknown) => {
        throw diskError(target, error);
      });
      let written = 0;
      try {
        const body = attempt.response.body;
        if (body !== null) {
          const reader = body.getReader();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            attempt.touch();
            written += value.byteLength;
            if (written > expected.size) {
              await reader.cancel().catch(() => undefined);
              throw new LibraryError("refused", `${expected.url} sent more than the ${expected.size} bytes Poly Haven publishes`);
            }
            hash.update(value);
            await handle.write(value).catch((error: unknown) => {
              throw diskError(target, error);
            });
          }
        }
      } finally {
        await handle.close();
      }
      if (written !== expected.size) {
        throw new LibraryError("refused", `${expected.url} sent ${written} bytes, but Poly Haven publishes ${expected.size}`);
      }
      const md5 = hash.digest("hex");
      if (md5 !== expected.md5) {
        throw new LibraryError("refused", `${expected.url} has md5 ${md5}, but Poly Haven publishes ${expected.md5}; the download is refused`);
      }
    }, signal);
    budget.left -= expected.size;
  }

  private async json<S extends z.ZodType>(key: string, url: string, schema: S, signal?: AbortSignal): Promise<z.infer<S>> {
    const cached = await this.cache.read(key);
    if (cached !== undefined) {
      const parsed = schema.safeParse(cached);
      if (parsed.success) return parsed.data;
      await this.cache.forget(key).catch(() => undefined);
    }
    const data = await this.http.get(url, "application/json", async (attempt) => {
      const body = await readCapped(attempt, MAX_JSON_BYTES, `the response from ${new URL(url).pathname}`);
      let value: unknown;
      try {
        value = JSON.parse(body.toString("utf8"));
      } catch {
        throw new LibraryError("invalid", `Poly Haven sent a response from ${new URL(url).pathname} that is not JSON`);
      }
      const parsed = schema.safeParse(value);
      if (!parsed.success) {
        throw new LibraryError("invalid", `Poly Haven sent an unexpected response from ${new URL(url).pathname}, so it was refused: ${describeIssues(parsed.error)}`);
      }
      return parsed.data as z.infer<S>;
    }, signal);
    await this.cache.write(key, data).catch(() => undefined);
    return data;
  }
}
