import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { describe, expect, it } from "vitest";
import type { BridgeAccess } from "../src/mcp/library/index.js";
import {
  BARREL,
  barrelBodies,
  filesUnder,
  HDRI_1K,
  HDRI_2K,
  interrupted,
  libraryHarness,
  type LibraryHarness,
  md5,
  serveBodies,
  textureUrl,
  withoutCache,
} from "./library-helpers.js";
import { texts } from "./mcp-helpers.js";

const NO_BRIDGE: BridgeAccess = { commands: [], request: () => Promise.reject(new Error("the bridge is not used")) };
const NOW = Date.parse("2027-01-15T08:00:00.000Z");
const HDR_BODY = Buffer.from("#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n\x80\x80\x80\x81");
const ASSET_FILES = ["library/", "library/hdri/", "library/hdri/abandoned_parking/", "library/hdri/abandoned_parking/LICENSE.json", "library/hdri/abandoned_parking/abandoned_parking_1k.hdr"];

async function download(harness: LibraryHarness, args: Record<string, unknown>): Promise<CallToolResult> {
  return harness.library.call("library_download", args, NO_BRIDGE);
}

async function downloaded(harness: LibraryHarness, args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const result = await download(harness, args);
  expect(result.isError, texts(result)).toBeFalsy();
  return JSON.parse(texts(result)) as Record<string, unknown>;
}

function assetFiles(harness: LibraryHarness): string[] {
  return withoutCache(filesUnder(harness.workspace.root)).filter((path) => path !== "library/.cache/");
}

function license(harness: LibraryHarness, type: string, id: string): unknown {
  return JSON.parse(readFileSync(join(harness.workspace.root, "library", type, id, "LICENSE.json"), "utf8"));
}

describe("library_download", () => {
  it("writes an HDRI and its LICENSE.json record", async () => {
    const harness = libraryHarness({ now: () => NOW });
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    const result = await downloaded(harness, { id: "abandoned_parking", resolution: "1k" });
    expect(result).toMatchObject({
      id: "abandoned_parking",
      type: "hdri",
      folder: "library/hdri/abandoned_parking",
      main: "library/hdri/abandoned_parking/abandoned_parking_1k.hdr",
      resolution: "1k",
      format: "hdr",
      license: "CC0-1.0",
      authors: ["Sergej Majboroda"],
      already_present: false,
    });
    expect(assetFiles(harness)).toEqual(ASSET_FILES);
    expect(readFileSync(join(harness.workspace.root, "library/hdri/abandoned_parking/abandoned_parking_1k.hdr")).equals(HDR_BODY)).toBe(true);
    expect(license(harness, "hdri", "abandoned_parking")).toEqual({
      asset: "abandoned_parking",
      name: "Abandoned Parking",
      type: "hdri",
      source: "https://polyhaven.com/a/abandoned_parking",
      license: "CC0-1.0",
      license_url: "https://creativecommons.org/publicdomain/zero/1.0/",
      authors: { "Sergej Majboroda": "All" },
      resolution: "1k",
      format: "hdr",
      main: "abandoned_parking_1k.hdr",
      files: [{ path: "abandoned_parking_1k.hdr", url: HDRI_1K, bytes: HDR_BODY.length, md5: md5(HDR_BODY) }],
      downloaded_at: "2027-01-15T08:00:00.000Z",
    });
  });

  it("fetches the PBR map set of a texture", async () => {
    const harness = libraryHarness({ now: () => NOW });
    const maps = { Diffuse: "diff", nor_gl: "nor_gl", Rough: "rough", AO: "ao", Displacement: "disp" };
    const bodies = new Map(Object.values(maps).map((map) => [textureUrl(map, "1k"), Buffer.from(`${map} pixels`)]));
    serveBodies(harness.polyHaven, "aerial_asphalt_01", bodies);
    const result = await downloaded(harness, { id: "aerial_asphalt_01", resolution: "1k" });
    const expectedMaps = Object.fromEntries(Object.entries(maps).map(([name, map]) => [name, `aerial_asphalt_01_${map}_1k.jpg`]));
    expect(result["maps"]).toEqual(expectedMaps);
    const record = license(harness, "texture", "aerial_asphalt_01") as { maps: unknown; files: { path: string }[]; main?: string; authors: unknown };
    expect(record.maps).toEqual(expectedMaps);
    expect(record.main).toBeUndefined();
    expect(record.authors).toEqual({ "Rob Tuytel": "All" });
    expect(record.files.map((file) => file.path).sort()).toEqual(Object.values(expectedMaps).sort());
    expect(harness.polyHaven.requested("https://dl.polyhaven.org/").sort()).toEqual([...bodies.keys()].sort());
  });

  it("fetches only the maps asked for, in the format asked for", async () => {
    const harness = libraryHarness();
    const bodies = new Map([
      [textureUrl("diff", "2k", "png"), Buffer.from("png diffuse")],
      [textureUrl("arm", "2k", "png"), Buffer.from("png arm")],
    ]);
    serveBodies(harness.polyHaven, "aerial_asphalt_01", bodies);
    const result = await downloaded(harness, { id: "aerial_asphalt_01", resolution: "2k", format: "png", maps: ["Diffuse", "arm"] });
    expect(result["maps"]).toEqual({ Diffuse: "aerial_asphalt_01_diff_2k.png", arm: "aerial_asphalt_01_arm_2k.png" });
  });

  it("fetches a model's glTF with the files it includes", async () => {
    const harness = libraryHarness();
    const bodies = barrelBodies();
    serveBodies(harness.polyHaven, "Barrel_01", bodies);
    const result = await downloaded(harness, { id: "Barrel_01", resolution: "1k" });
    expect(result["main"]).toBe("library/model/Barrel_01/Barrel_01_1k.gltf");
    expect(assetFiles(harness).filter((path) => path.startsWith("library/model/"))).toEqual([
      "library/model/",
      "library/model/Barrel_01/",
      "library/model/Barrel_01/Barrel_01.bin",
      "library/model/Barrel_01/Barrel_01_1k.gltf",
      "library/model/Barrel_01/LICENSE.json",
      "library/model/Barrel_01/textures/",
      "library/model/Barrel_01/textures/Barrel_01_explosive_arm_1k.jpg",
      "library/model/Barrel_01/textures/Barrel_01_explosive_diff_1k.jpg",
      "library/model/Barrel_01/textures/Barrel_01_explosive_nor_gl_1k.jpg",
    ]);
    expect(readFileSync(join(harness.workspace.root, "library/model/Barrel_01/textures/Barrel_01_explosive_diff_1k.jpg"), "utf8")).toBe("diffuse jpeg");
    expect(harness.polyHaven.requested("https://dl.polyhaven.org/").sort()).toEqual(Object.values(BARREL).sort());
  });

  it("serves an asset already in the library without the network", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    await downloaded(harness, { id: "abandoned_parking", resolution: "1k" });
    harness.polyHaven.offline = true;
    const seen = harness.polyHaven.seen.length;
    const again = await downloaded(harness, { id: "abandoned_parking", resolution: "1k", format: "hdr" });
    expect(again["already_present"]).toBe(true);
    expect(harness.polyHaven.seen.length).toBe(seen);
    const other = await download(harness, { id: "abandoned_parking", resolution: "2k" });
    expect(texts(other)).toMatch(/^offline: Poly Haven is unreachable, .*library_download needs the network\. Assets already downloaded/);
  });

  it("replaces an asset downloaded at another resolution in one step", async () => {
    const harness = libraryHarness();
    const twoK = Buffer.from("two k sky");
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY], [HDRI_2K, twoK]]));
    await downloaded(harness, { id: "abandoned_parking", resolution: "1k" });
    const result = await downloaded(harness, { id: "abandoned_parking", resolution: "2k" });
    expect(result["already_present"]).toBe(false);
    expect(assetFiles(harness)).toEqual([...ASSET_FILES.slice(0, 4), "library/hdri/abandoned_parking/abandoned_parking_2k.hdr"]);
    expect((license(harness, "hdri", "abandoned_parking") as { resolution: string }).resolution).toBe("2k");
  });
});

describe("checksums", () => {
  it("refuses a file whose md5 differs from the published one, and leaves nothing behind", async () => {
    const harness = libraryHarness();
    const files = serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]])) as { hdri: Record<string, Record<string, { md5: string }>> };
    const tampered = Buffer.from(HDR_BODY);
    tampered[tampered.length - 1] = 0x82;
    harness.polyHaven.route(HDRI_1K, () => new Response(new Uint8Array(tampered), { headers: { "content-length": String(tampered.length) } }));
    const result = await download(harness, { id: "abandoned_parking", resolution: "1k" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toBe(
      `refused: ${HDRI_1K} has md5 ${md5(tampered)}, but Poly Haven publishes ${files.hdri["1k"]?.["hdr"]?.md5}; the download is refused`,
    );
    expect(assetFiles(harness)).toEqual(["library/"]);
    expect(harness.polyHaven.requested(HDRI_1K)).toHaveLength(1);
  });

  it("refuses a texture set when one map is corrupt, keeping none of the others", async () => {
    const harness = libraryHarness();
    const bodies = new Map(["diff", "nor_gl", "rough", "ao", "disp"].map((map) => [textureUrl(map, "1k"), Buffer.from(`${map} pixels`)]));
    serveBodies(harness.polyHaven, "aerial_asphalt_01", bodies);
    harness.polyHaven.route(textureUrl("ao", "1k"), () => new Response(new Uint8Array(Buffer.from("AO pixels")), { headers: { "content-length": "9" } }));
    const result = await download(harness, { id: "aerial_asphalt_01", resolution: "1k" });
    expect(texts(result)).toContain("aerial_asphalt_01_ao_1k.jpg has md5");
    expect(assetFiles(harness)).toEqual(["library/"]);
  });

  it("refuses a file larger or smaller than published", async () => {
    for (const body of [Buffer.concat([HDR_BODY, Buffer.from("x")]), HDR_BODY.subarray(1)]) {
      const harness = libraryHarness();
      serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
      harness.polyHaven.route(HDRI_1K, () => new Response(new Uint8Array(body)));
      const result = await download(harness, { id: "abandoned_parking", resolution: "1k" });
      expect(texts(result)).toMatch(/^refused: .*(sent more than|sent \d+ bytes, but Poly Haven publishes)/);
      expect(assetFiles(harness)).toEqual(["library/"]);
    }
  });
});

describe("atomic downloads", () => {
  it("leaves nothing behind when the connection drops mid-file", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    harness.polyHaven.route(HDRI_1K, () => interrupted(HDR_BODY, 10));
    const result = await download(harness, { id: "abandoned_parking", resolution: "1k" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toContain("after 3 attempts (UND_ERR_SOCKET: other side closed)");
    expect(harness.polyHaven.requested(HDRI_1K)).toHaveLength(3);
    expect(assetFiles(harness)).toEqual(["library/"]);
  });

  it("recovers when a retry succeeds after a drop", async () => {
    const harness = libraryHarness();
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY]]));
    let calls = 0;
    harness.polyHaven.route(HDRI_1K, () => {
      calls += 1;
      return calls === 1 ? interrupted(HDR_BODY, 10) : new Response(new Uint8Array(HDR_BODY));
    });
    await downloaded(harness, { id: "abandoned_parking", resolution: "1k" });
    expect(readFileSync(join(harness.workspace.root, "library/hdri/abandoned_parking/abandoned_parking_1k.hdr")).equals(HDR_BODY)).toBe(true);
  });

  it("keeps the earlier download intact when a replacement fails", async () => {
    const harness = libraryHarness({ now: () => NOW });
    serveBodies(harness.polyHaven, "abandoned_parking", new Map([[HDRI_1K, HDR_BODY], [HDRI_2K, Buffer.from("two k")]]));
    await downloaded(harness, { id: "abandoned_parking", resolution: "1k" });
    const before = license(harness, "hdri", "abandoned_parking");
    harness.polyHaven.route(HDRI_2K, () => interrupted(Buffer.from("two k"), 2));
    expect((await download(harness, { id: "abandoned_parking", resolution: "2k" })).isError).toBe(true);
    expect(assetFiles(harness)).toEqual(ASSET_FILES);
    expect(license(harness, "hdri", "abandoned_parking")).toEqual(before);
  });

  it("leaves nothing behind when a model's second file drops", async () => {
    const harness = libraryHarness();
    const bodies = barrelBodies();
    serveBodies(harness.polyHaven, "Barrel_01", bodies);
    harness.polyHaven.route(BARREL.arm, () => interrupted(bodies.get(BARREL.arm) as Buffer, 3));
    expect((await download(harness, { id: "Barrel_01", resolution: "1k" })).isError).toBe(true);
    expect(assetFiles(harness)).toEqual(["library/"]);
  });
});
