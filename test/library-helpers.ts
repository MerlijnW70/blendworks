import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { Library, type LibraryOptions } from "../src/mcp/library/index.js";
import type { FetchLike } from "../src/mcp/library/http.js";
import { Workspace } from "../src/mcp/workspace.js";
import { scratchDir } from "./mcp-helpers.js";

export const FIXTURES = join("test", "fixtures", "polyhaven");

export function fixture(name: string): unknown {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));
}

export function md5(data: Buffer): string {
  return createHash("md5").update(data).digest("hex");
}

export type Route = (url: URL, init: RequestInit) => Response | Promise<Response>;

export interface SeenRequest {
  url: string;
  userAgent: string | null;
  redirect: RequestInit["redirect"];
}

export function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
}

export function bytes(data: Buffer, status = 200): Response {
  return new Response(new Uint8Array(data), { status, headers: { "content-length": String(data.length) } });
}

export function offlineError(): TypeError {
  const cause = Object.assign(new Error("getaddrinfo ENOTFOUND api.polyhaven.com"), { code: "ENOTFOUND" });
  return new TypeError("fetch failed", { cause });
}

export class FakePolyHaven {
  readonly seen: SeenRequest[] = [];
  readonly routes = new Map<string, Route>();
  offline = false;

  constructor() {
    for (const type of ["hdris", "textures", "models"]) {
      this.json(`https://api.polyhaven.com/assets?t=${type}`, fixture(`assets-${type}.json`));
      this.json(`https://api.polyhaven.com/categories/${type}`, fixture(`categories-${type}.json`));
    }
    for (const id of ["abandoned_parking", "aerial_asphalt_01", "Barrel_01"]) {
      this.json(`https://api.polyhaven.com/info/${id}`, fixture(`info-${id}.json`));
      this.json(`https://api.polyhaven.com/files/${id}`, fixture(`files-${id}.json`));
    }
    const listings = ["hdris", "textures", "models"].map((type) => fixture(`assets-${type}.json`) as Record<string, { type: number }>);
    const templates: Record<number, [string, string]> = { 0: ["abandoned_parking", "files-abandoned_parking.json"], 1: ["aerial_asphalt_01", "files-aerial_asphalt_01.json"], 2: ["Barrel_01", "files-Barrel_01.json"] };
    for (const listing of listings) {
      for (const [id, asset] of Object.entries(listing)) {
        const url = `https://api.polyhaven.com/files/${id}`;
        if (this.routes.has(url)) continue;
        const [templateId, file] = templates[asset.type] as [string, string];
        this.json(url, JSON.parse(readFileSync(join(FIXTURES, file), "utf8").split(templateId).join(id)));
      }
    }
  }

  json(url: string, value: unknown): void {
    this.routes.set(url, () => json(value));
  }

  route(url: string, route: Route): void {
    this.routes.set(url, route);
  }

  serveFiles(id: string, files: unknown): void {
    this.json(`https://api.polyhaven.com/files/${id}`, files);
  }

  readonly fetch: FetchLike = async (raw, init) => {
    const headers = new Headers(init.headers);
    this.seen.push({ url: raw, userAgent: headers.get("user-agent"), redirect: init.redirect });
    if (this.offline) throw offlineError();
    const url = new URL(raw);
    const route = this.routes.get(url.href) ?? this.routes.get(`${url.origin}${url.pathname}`);
    if (route === undefined) return new Response(`No asset at ${url.pathname}`, { status: 404 });
    return route(url, init);
  };

  requested(prefix: string): string[] {
    return this.seen.map((request) => request.url).filter((url) => url.startsWith(prefix));
  }
}

export interface LibraryHarness {
  library: Library;
  workspace: Workspace;
  polyHaven: FakePolyHaven;
  sleeps: number[];
}

export function libraryHarness(options: Partial<LibraryOptions> = {}): LibraryHarness {
  const workspace = Workspace.open(join(scratchDir(), "workspace"));
  const polyHaven = new FakePolyHaven();
  const sleeps: number[] = [];
  const library = new Library({
    workspace,
    fetch: polyHaven.fetch,
    retries: 2,
    backoffMs: 10,
    sleep: async (ms) => {
      sleeps.push(ms);
    },
    ...options,
  });
  return { library, workspace, polyHaven, sleeps };
}

export function filesUnder(root: string): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    let names: string[];
    try {
      names = readdirSync(dir);
    } catch {
      return;
    }
    for (const name of names) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) {
        out.push(`${relative(root, path).split(sep).join("/")}/`);
        walk(path);
      } else out.push(relative(root, path).split(sep).join("/"));
    }
  };
  walk(root);
  return out.sort();
}

export function withoutCache(paths: string[]): string[] {
  return paths.filter((path) => !path.startsWith("library/.cache/"));
}

function rewrite(value: unknown, bodies: Map<string, Buffer>): unknown {
  if (Array.isArray(value)) return value.map((entry) => rewrite(entry, bodies));
  if (typeof value !== "object" || value === null) return value;
  const out: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) out[key] = rewrite(entry, bodies);
  const url = out["url"];
  const body = typeof url === "string" ? bodies.get(url) : undefined;
  if (body !== undefined) {
    out["size"] = body.length;
    out["md5"] = md5(body);
  }
  return out;
}

export function serveBodies(polyHaven: FakePolyHaven, id: string, bodies: Map<string, Buffer>): unknown {
  const files = rewrite(fixture(`files-${id}.json`), bodies);
  polyHaven.serveFiles(id, files);
  for (const [url, body] of bodies) polyHaven.route(url, () => bytes(body));
  return files;
}

export function interrupted(data: Buffer, after: number): Response {
  let sent = false;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (!sent) {
        sent = true;
        controller.enqueue(new Uint8Array(data.subarray(0, after)));
        return;
      }
      controller.error(new TypeError("terminated", { cause: Object.assign(new Error("other side closed"), { code: "UND_ERR_SOCKET" }) }));
    },
  });
  return new Response(stream, { status: 200, headers: { "content-length": String(data.length) } });
}

export const HDRI_1K = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/abandoned_parking_1k.hdr";
export const HDRI_2K = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/abandoned_parking_2k.hdr";

export function textureUrl(map: string, resolution: string, format = "jpg"): string {
  return `https://dl.polyhaven.org/file/ph-assets/Textures/${format}/${resolution}/aerial_asphalt_01/aerial_asphalt_01_${map}_${resolution}.${format}`;
}

export const BARREL = {
  gltf: "https://dl.polyhaven.org/file/ph-assets/Models/gltf/1k/Barrel_01/Barrel_01_1k.gltf",
  bin: "https://dl.polyhaven.org/file/ph-assets/Models/gltf/8k/Barrel_01/Barrel_01.bin",
  diff: "https://dl.polyhaven.org/file/ph-assets/Models/jpg/1k/Barrel_01/Barrel_01_explosive_diff_1k.jpg",
  nor: "https://dl.polyhaven.org/file/ph-assets/Models/jpg/1k/Barrel_01/Barrel_01_explosive_nor_gl_1k.jpg",
  arm: "https://dl.polyhaven.org/file/ph-assets/Models/jpg/1k/Barrel_01/Barrel_01_explosive_arm_1k.jpg",
};

export function barrelGltf(images: string[] = ["textures/Barrel_01_explosive_diff_1k.jpg", "textures/Barrel_01_explosive_nor_gl_1k.jpg", "textures/Barrel_01_explosive_arm_1k.jpg"]): Buffer {
  return Buffer.from(JSON.stringify({ asset: { version: "2.0" }, buffers: [{ uri: "Barrel_01.bin", byteLength: 12 }], images: images.map((uri) => ({ uri })) }));
}

export function barrelBodies(gltf: Buffer = barrelGltf()): Map<string, Buffer> {
  return new Map([
    [BARREL.gltf, gltf],
    [BARREL.bin, Buffer.from("binary-bytes")],
    [BARREL.diff, Buffer.from("diffuse jpeg")],
    [BARREL.nor, Buffer.from("normal jpeg")],
    [BARREL.arm, Buffer.from("arm jpeg")],
  ]);
}
