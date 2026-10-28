import { mkdirSync, readdirSync, symlinkSync } from "node:fs";
import { join } from "node:path";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { describe, expect, it } from "vitest";
import { LibraryError } from "../src/mcp/library/common.js";
import { DEFAULT_MAX_BYTES, type BridgeAccess } from "../src/mcp/library/index.js";
import { planDownload } from "../src/mcp/library/plan.js";
import type { SetFiles } from "../src/mcp/library/schemas.js";
import { BARREL, barrelBodies, barrelGltf, filesUnder, fixture, HDRI_1K, libraryHarness, type LibraryHarness, serveBodies, withoutCache } from "./library-helpers.js";
import { scratchDir, texts } from "./mcp-helpers.js";

const NO_BRIDGE: BridgeAccess = { commands: [], request: () => Promise.reject(new Error("the bridge is not used")) };
const HDR_BODY = Buffer.from("tiny hdr bytes");

async function call(harness: LibraryHarness, name: string, args: Record<string, unknown>): Promise<CallToolResult> {
  return harness.library.call(name, args, NO_BRIDGE);
}

function assetFiles(harness: LibraryHarness): string[] {
  return withoutCache(filesUnder(harness.workspace.root)).filter((path) => path !== "library/.cache/");
}

function planError(run: () => unknown): string {
  try {
    run();
  } catch (error) {
    expect(error).toBeInstanceOf(LibraryError);
    return (error as LibraryError).message;
  }
  throw new Error("expected a refusal");
}

describe("host refusals", () => {
  it("refuses a download redirected to a foreign host, without following it", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    harness.polyHaven.route(HDRI_1K, () => new Response(null, { status: 302, headers: { location: "https://downloads.evil.example/sky.hdr" } }));
    harness.polyHaven.route("https://downloads.evil.example/sky.hdr", () => new Response(new Uint8Array(HDR_BODY)));
    const result = await call(harness, "library_download", { id: "abandoned_parking", resolution: "1k" });
    expect(texts(result)).toBe(
      "refused: refused a redirect from dl.polyhaven.org to https://downloads.evil.example/sky.hdr: downloads.evil.example is not a Poly Haven host; only api.polyhaven.com, dl.polyhaven.org, cdn.polyhaven.com are fetched",
    );
    expect(harness.polyHaven.requested("https://downloads.evil.example")).toEqual([]);
    expect(assetFiles(harness)).toEqual(["library/"]);
  });

  it("follows a redirect that stays on Poly Haven hosts", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    harness.polyHaven.route(HDRI_1K, () => new Response(null, { status: 307, headers: { location: "/mirror/abandoned_parking_1k.hdr" } }));
    harness.polyHaven.route("https://dl.polyhaven.org/mirror/abandoned_parking_1k.hdr", () => new Response(new Uint8Array(HDR_BODY)));
    expect((await call(harness, "library_download", { id: "abandoned_parking", resolution: "1k" })).isError).toBeFalsy();
  });

  it("refuses a thumbnail redirected to a foreign host", async () => {
    const harness = libraryHarness();
    harness.polyHaven.route("https://cdn.polyhaven.com/asset_img/thumbs/abandoned_parking.png", () => new Response(null, { status: 301, headers: { location: "https://evil.example/t.png" } }));
    const result = await call(harness, "library_preview", { id: "abandoned_parking" });
    expect(texts(result)).toMatch(/^refused: refused a redirect from cdn\.polyhaven\.com to https:\/\/evil\.example\/t\.png/);
    expect(harness.polyHaven.requested("https://evil.example")).toEqual([]);
  });

  it("refuses file listings that point at other hosts", async () => {
    const harness = libraryHarness();
    const files = fixture("files-abandoned_parking.json") as { hdri: Record<string, Record<string, { url: string }>> };
    (files.hdri["1k"] as Record<string, { url: string }>)["hdr"] = { ...files.hdri["1k"]?.["hdr"], url: "https://evil.example/abandoned_parking_1k.hdr" } as { url: string };
    harness.polyHaven.serveFiles("abandoned_parking", files);
    const result = await call(harness, "library_download", { id: "abandoned_parking", resolution: "1k" });
    expect(texts(result)).toMatch(/^refused: this HDRI at 1k \(abandoned_parking_1k\.hdr\) is listed badly by Poly Haven \(url is not an https URL on a Poly Haven host\)/);
    expect(harness.polyHaven.requested("https://evil.example")).toEqual([]);
  });
});

describe("path refusals", () => {
  it("refuses path traversal in an id before any request", async () => {
    const harness = libraryHarness();
    for (const id of ["../escape", "..", "a/b", "..\\escape", "%2e%2e", "/abs", "C:\\x", "x".repeat(81)]) {
      for (const [tool, extra] of [["library_download", { resolution: "1k" }], ["library_preview", {}], ["library_apply", {}]] as const) {
        const result = await call(harness, tool, { id, ...extra });
        expect(result.isError).toBe(true);
        expect(texts(result)).toMatch(/^refused: bad arguments: id: is not a Poly Haven asset id/);
      }
    }
    expect(harness.polyHaven.seen).toEqual([]);
    expect(readdirSync(harness.workspace.root)).toEqual([]);
  });

  it("refuses file paths in a listing that leave the asset folder", async () => {
    for (const path of ["../escape.bin", "textures/../../escape.jpg", "/etc/escape", "C:/escape.bin", "textures\\..\\escape.jpg", "textures/./x.jpg", "", "LICENSE.json"]) {
      const harness = libraryHarness();
      const files = fixture("files-Barrel_01.json") as SetFiles;
      const gltf = files["gltf"]?.["1k"]?.["gltf"] as { include?: Record<string, unknown> } | undefined;
      if (gltf === undefined) throw new Error("fixture lacks the 1k glTF");
      gltf.include = { [path]: { url: BARREL.bin, size: 12, md5: "0".repeat(32) } };
      harness.polyHaven.serveFiles("Barrel_01", files);
      const result = await call(harness, "library_download", { id: "Barrel_01", resolution: "1k" });
      expect(result.isError, path).toBe(true);
      expect(texts(result)).toMatch(/^refused: /);
      expect(harness.polyHaven.requested("https://dl.polyhaven.org/")).toEqual([]);
      expect(assetFiles(harness)).toEqual(["library/"]);
    }
  });

  it("refuses a file URL whose name decodes to a traversal", async () => {
    const harness = libraryHarness();
    const files = fixture("files-abandoned_parking.json") as { hdri: Record<string, Record<string, { url: string }>> };
    const entry = files.hdri["1k"]?.["hdr"] as { url: string };
    entry.url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/..%2F..%2Fescape.hdr";
    harness.polyHaven.serveFiles("abandoned_parking", files);
    const result = await call(harness, "library_download", { id: "abandoned_parking", resolution: "1k" });
    expect(texts(result)).toBe('refused: "../../escape.hdr" is not a safe file path inside an asset folder');
  });

  it("refuses a glTF that refers to files Poly Haven does not list for it", async () => {
    for (const uri of ["../../outside.png", "https://evil.example/x.png", "textures/unlisted.jpg"]) {
      const harness = libraryHarness();
      serveBodies(harness.polyHaven, "Barrel_01", barrelBodies(barrelGltf(["textures/Barrel_01_explosive_diff_1k.jpg", uri])));
      const result = await call(harness, "library_download", { id: "Barrel_01", resolution: "1k" });
      expect(texts(result)).toBe(`refused: the glTF refers to ${uri}, which is not one of the files Poly Haven lists for it`);
      expect(assetFiles(harness)).toEqual(["library/"]);
    }
  });

  it("refuses to write through a library folder that links outside the workspace", async () => {
    const harness = libraryHarness();
    const outside = join(scratchDir(), "outside");
    mkdirSync(outside);
    symlinkSync(outside, join(harness.workspace.root, "library"), "junction");
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    const result = await call(harness, "library_download", { id: "abandoned_parking", resolution: "1k" });
    expect(texts(result)).toMatch(/^refused: "library\/.*" is outside the workspace/);
    expect(readdirSync(outside)).toEqual([]);
  });
});

describe("size and resolution refusals", () => {
  it("refuses a resolution above the size cap before fetching any file", async () => {
    const harness = libraryHarness({ maxBytes: 30_000_000 });
    const result = await call(harness, "library_download", { id: "aerial_asphalt_01", resolution: "4k", format: "png" });
    expect(texts(result)).toBe("refused: 4k png is 111.5 MB, above the download cap of 30.0 MB; 1k, 2k fit");
    expect(harness.polyHaven.requested("https://dl.polyhaven.org/")).toEqual([]);
    expect(assetFiles(harness)).toEqual(["library/"]);
  });

  it("has a default cap that takes 2K and 4K texture sets and refuses 8K PNG and EXR", () => {
    const files = fixture("files-aerial_asphalt_01.json") as SetFiles;
    expect(DEFAULT_MAX_BYTES).toBe(300_000_000);
    for (const [resolution, format, total] of [["2k", "png", 29_148_894], ["4k", "jpg", 36_560_827], ["4k", "exr", 87_603_634], ["4k", "png", 111_538_630]] as const) {
      expect(planDownload("texture", files, { resolution, format }, DEFAULT_MAX_BYTES).total).toBe(total);
    }
    expect(planError(() => planDownload("texture", files, { resolution: "8k", format: "png" }, DEFAULT_MAX_BYTES))).toBe(
      "8k png is 403.8 MB, above the download cap of 300.0 MB; 1k, 2k, 4k fit",
    );
    expect(planError(() => planDownload("texture", files, { resolution: "8k", format: "exr" }, DEFAULT_MAX_BYTES))).toContain("341.6 MB");
  });

  it("refuses resolutions, formats and maps the asset does not offer", async () => {
    const harness = libraryHarness();
    const cases: [Record<string, unknown>, string][] = [
      [{ id: "abandoned_parking", resolution: "32k" }, "refused: this HDRI has no 32k resolution; it offers 1k, 2k, 4k, 8k, 16k"],
      [{ id: "abandoned_parking", resolution: "1k", format: "jpg" }, "refused: a hdri downloads as hdr or exr, not jpg"],
      [{ id: "abandoned_parking", resolution: "1k", maps: ["Diffuse"] }, "refused: maps applies only to textures"],
      [{ id: "Barrel_01", resolution: "1k", format: "hdr" }, "refused: a model downloads as gltf, not hdr"],
      [{ id: "aerial_asphalt_01", resolution: "1k", maps: ["Sparkle"] }, "refused: this texture has no map Sparkle; it offers Diffuse, nor_dx, nor_gl, rough_ao, arm, AO, Displacement, Rough"],
      [{ id: "aerial_asphalt_01", resolution: "huge" }, 'refused: bad arguments: resolution: is not a resolution such as "1k", "2k" or "4k"'],
    ];
    for (const [args, message] of cases) {
      const result = await call(harness, "library_download", args);
      expect(result.isError).toBe(true);
      expect(texts(result).startsWith(message), `${texts(result)} should start with ${message}`).toBe(true);
    }
    expect(harness.polyHaven.requested("https://dl.polyhaven.org/")).toEqual([]);
  });
});
