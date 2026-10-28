import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { describe, expect, it } from "vitest";
import type { BridgeAccess } from "../src/mcp/library/index.js";
import { commandsFromDescribe } from "../src/mcp/schema.js";
import { BARREL, barrelBodies, HDRI_1K, libraryHarness, type LibraryHarness, serveBodies, textureUrl } from "./library-helpers.js";
import { texts } from "./mcp-helpers.js";

const NO_BRIDGE: BridgeAccess = { commands: [], request: () => Promise.reject(new Error("the bridge is not used")) };
const BAD_MD5 = "not-an-md5";

type Files = Record<string, Record<string, Record<string, { md5?: string; include?: Record<string, { md5?: string; size?: number }> }>>>;

function run(harness: LibraryHarness, name: string, args: Record<string, unknown>, signal?: AbortSignal): Promise<CallToolResult> {
  return harness.library.call(name, args, NO_BRIDGE, signal);
}

function barrelWithBad8k(harness: LibraryHarness): void {
  const files = serveBodies(harness.polyHaven, "Barrel_01", barrelBodies()) as Files;
  const include = files["gltf"]?.["8k"]?.["gltf"]?.include;
  if (include === undefined) throw new Error("the fixture lacks the 8k glTF includes");
  include["Barrel_01.bin"] = { ...include["Barrel_01.bin"], md5: BAD_MD5 };
  harness.polyHaven.serveFiles("Barrel_01", files);
}

describe("a listing with one bad 8k file", () => {
  it("still downloads the 1k set, strictly verified", async () => {
    const harness = libraryHarness();
    barrelWithBad8k(harness);
    const result = await run(harness, "library_download", { id: "Barrel_01", resolution: "1k" });
    expect(result.isError, texts(result)).toBeFalsy();
    expect(JSON.parse(texts(result))).toMatchObject({ id: "Barrel_01", resolution: "1k", already_present: false });
    expect(harness.polyHaven.requested(BARREL.bin)).toHaveLength(1);
  });

  it("refuses the 8k set naming the bad file and suggests the other resolutions, without downloading anything", async () => {
    const harness = libraryHarness();
    barrelWithBad8k(harness);
    const result = await run(harness, "library_download", { id: "Barrel_01", resolution: "8k" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/^refused: this model at 8k \(Barrel_01_8k\.gltf\) is listed badly by Poly Haven \(include\.Barrel_01\.bin\.md5 .*\), so it is not downloaded; use another resolution, 1k, 2k, 4k$/);
    expect(harness.polyHaven.requested("https://dl.polyhaven.org/")).toEqual([]);
  });

  it("only checks the maps that were chosen in a texture set", async () => {
    const harness = libraryHarness();
    const bodies = new Map([[textureUrl("diff", "1k"), Buffer.from("diffuse")]]);
    const files = serveBodies(harness.polyHaven, "aerial_asphalt_01", bodies) as Files;
    const rough = files["Rough"]?.["8k"]?.["jpg"];
    if (rough === undefined) throw new Error("the fixture lacks the 8k roughness map");
    rough.md5 = BAD_MD5;
    harness.polyHaven.serveFiles("aerial_asphalt_01", files);
    const fine = await run(harness, "library_download", { id: "aerial_asphalt_01", resolution: "1k", maps: ["Diffuse"] });
    expect(fine.isError, texts(fine)).toBeFalsy();
    const bad = await run(harness, "library_download", { id: "aerial_asphalt_01", resolution: "8k", maps: ["Rough"] });
    expect(texts(bad)).toMatch(/^refused: the Rough map at 8k \(aerial_asphalt_01_rough_8k\.jpg\) is listed badly by Poly Haven \(md5 .*\), so it is not downloaded; use another resolution, 1k, 2k, 4k$/);
  });

  it("still refuses a download whose bytes do not match the listed md5", async () => {
    const harness = libraryHarness();
    const bodies = new Map([[HDRI_1K, Buffer.from("tiny hdr")]]);
    const files = serveBodies(harness.polyHaven, "abandoned_parking", bodies) as { hdri: Record<string, Record<string, { md5: string }>> };
    const entry = files.hdri["1k"]?.["hdr"];
    if (entry === undefined) throw new Error("the fixture lacks the 1k HDRI");
    entry.md5 = "0".repeat(32);
    harness.polyHaven.serveFiles("abandoned_parking", files);
    const result = await run(harness, "library_download", { id: "abandoned_parking", resolution: "1k" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/has md5 .*, but Poly Haven publishes 0{32}; the download is refused/);
  });
});

describe("a search page with one bad asset", () => {
  it("lists the others and names the unavailable one with a reason", async () => {
    const harness = libraryHarness();
    harness.polyHaven.serveFiles("blue_photo_studio", { hdri: "nothing here" });
    const result = await run(harness, "library_search", { type: "hdri", per_page: 24 });
    expect(result.isError, texts(result)).toBeFalsy();
    const page = JSON.parse(texts(result)) as { total: number; results: { id: string }[]; unavailable?: { id: string; name: string; reason: string }[] };
    expect(page.total).toBe(7);
    expect(page.results.map((entry) => entry.id)).not.toContain("blue_photo_studio");
    expect(page.results).toHaveLength(6);
    expect(page.unavailable).toHaveLength(1);
    expect(page.unavailable?.[0]).toMatchObject({ id: "blue_photo_studio", name: "Blue Photo Studio" });
    expect(page.unavailable?.[0]?.reason).toMatch(/unexpected response from \/files\/blue_photo_studio/);
  });

  it("does not list unavailable assets when every file listing is fine, and keeps 8k resolutions of a loosely bad listing", async () => {
    const harness = libraryHarness();
    barrelWithBad8k(harness);
    const result = await run(harness, "library_search", { type: "model", query: "barrel" });
    const page = JSON.parse(texts(result)) as { results: { id: string; resolutions: string[] }[]; unavailable?: unknown };
    expect(page.results).toEqual([expect.objectContaining({ id: "Barrel_01", resolutions: ["1k", "2k", "4k", "8k"] })]);
    expect(page.unavailable).toBeUndefined();
  });

  it("still fails as offline when every lookup was offline", async () => {
    const harness = libraryHarness();
    await run(harness, "library_search", { type: "hdri" });
    harness.polyHaven.offline = true;
    const other = libraryHarness({ fetch: harness.polyHaven.fetch });
    const result = await run(other, "library_search", { type: "hdri" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/^offline: /);
  });
});

describe("cancellation", () => {
  function hang(harness: LibraryHarness, url: string): void {
    harness.polyHaven.route(
      url,
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
  }

  it("stops a search that waits for Poly Haven", async () => {
    const harness = libraryHarness();
    hang(harness, "https://api.polyhaven.com/assets?t=hdris");
    const controller = new AbortController();
    const pending = run(harness, "library_search", { type: "hdri" }, controller.signal);
    setTimeout(() => controller.abort(), 30);
    const result = await pending;
    expect(result.isError).toBe(true);
    expect(texts(result)).toBe("cancelled: the request was cancelled");
    expect(harness.sleeps).toEqual([]);
  });

  it("stops a download in the middle of a file and leaves nothing behind", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, Buffer.from("tiny hdr")]]));
    hang(harness, HDRI_1K);
    const controller = new AbortController();
    const pending = run(harness, "library_download", { id: "abandoned_parking", resolution: "1k" }, controller.signal);
    setTimeout(() => controller.abort(), 50);
    const result = await pending;
    expect(texts(result)).toBe("cancelled: the request was cancelled");
    const again = await run(harness, "library_download", { id: "abandoned_parking", resolution: "1k" }, AbortSignal.abort());
    expect(texts(again)).toMatch(/^cancelled: library_download was cancelled before it started/);
  });

  it("hands the signal on to the bridge when it applies an asset", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, Buffer.from("tiny hdr")]]));
    expect((await run(harness, "library_download", { id: "abandoned_parking", resolution: "1k" })).isError).toBeFalsy();
    const commands = commandsFromDescribe({
      protocol: 1,
      commands: [{ name: "set_world_hdri", description: "Light the world.", schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] }, mutates: true, destructive: false, writes_files: false, timeout: 120, max_timeout: 600 }],
    });
    const seen: (AbortSignal | undefined)[] = [];
    const bridge: BridgeAccess = {
      commands,
      request: async (_cmd, _args, options) => {
        seen.push(options?.signal);
        return { result: { ok: true }, notices: [] };
      },
    };
    const controller = new AbortController();
    const result = await harness.library.call("library_apply", { id: "abandoned_parking" }, bridge, controller.signal);
    expect(result.isError, texts(result)).toBeFalsy();
    expect(seen).toEqual([controller.signal]);
  });
});
