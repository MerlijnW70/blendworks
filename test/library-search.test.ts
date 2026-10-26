import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { describe, expect, it } from "vitest";
import type { BridgeAccess } from "../src/mcp/library/index.js";
import { libraryHarness, type LibraryHarness } from "./library-helpers.js";
import { texts } from "./mcp-helpers.js";

const NO_BRIDGE: BridgeAccess = {
  commands: [],
  request: () => Promise.reject(new Error("the bridge is not used")),
};

interface Result {
  id: string;
  name: string;
  type: string;
  categories: string[];
  tags: string[];
  dimensions_m?: number[];
  max_resolution_px: number[];
  resolutions: string[];
}

interface Page {
  total: number;
  page: number;
  pages: number;
  per_page: number;
  results: Result[];
}

async function search(harness: LibraryHarness, args: Record<string, unknown>): Promise<Page> {
  const result = await harness.library.call("library_search", args, NO_BRIDGE);
  expect(result.isError, texts(result)).toBeFalsy();
  return JSON.parse(texts(result)) as Page;
}

async function refused(harness: LibraryHarness, args: Record<string, unknown>): Promise<CallToolResult> {
  const result = await harness.library.call("library_search", args, NO_BRIDGE);
  expect(result.isError).toBe(true);
  return result;
}

describe("library_search", () => {
  it("lists one type, most downloaded first, with id, name, type, categories, dimensions and resolutions", async () => {
    const harness = libraryHarness();
    const page = await search(harness, { type: "texture" });
    expect(page.total).toBe(6);
    expect(page.results.map((result) => result.id)).toEqual(["metal_plate", "aerial_asphalt_01", "leafy_grass", "american_walnut_veneer", "ash_veneer", "angli_veneer"]);
    const asphalt = page.results.find((result) => result.id === "aerial_asphalt_01");
    expect(asphalt).toMatchObject({
      name: "Aerial Asphalt 01",
      type: "texture",
      categories: ["asphalt", "outdoor", "floor", "road", "man made", "aerial"],
      dimensions_m: [30, 30],
      max_resolution_px: [8192, 8192],
      resolutions: ["1k", "2k", "4k", "8k"],
    });
  });

  it("orders by download count and reads resolutions from each asset's files", async () => {
    const harness = libraryHarness();
    const page = await search(harness, { type: "hdri", per_page: 24 });
    expect(page.results.map((result) => result.id)).toEqual([
      "brown_photostudio_01",
      "blue_photo_studio",
      "blocky_photo_studio",
      "abandoned_parking",
      "blaubeuren_night",
      "blaubeuren_church_square",
      "aarfontein_dawn_2",
    ]);
    const parking = page.results.find((result) => result.id === "abandoned_parking");
    expect(parking?.resolutions).toEqual(["1k", "2k", "4k", "8k", "16k"]);
    expect(parking?.max_resolution_px).toEqual([16384, 8192]);
    expect(parking?.dimensions_m).toBeUndefined();
    expect(harness.polyHaven.requested("https://api.polyhaven.com/files/")).toHaveLength(7);
  });

  it("pages through the matches", async () => {
    const harness = libraryHarness();
    const all = await search(harness, { type: "hdri", per_page: 24 });
    expect(all.total).toBe(7);
    const first = await search(harness, { type: "hdri", per_page: 3, page: 1 });
    const second = await search(harness, { type: "hdri", per_page: 3, page: 2 });
    const third = await search(harness, { type: "hdri", per_page: 3, page: 3 });
    const beyond = await search(harness, { type: "hdri", per_page: 3, page: 4 });
    expect([first.pages, first.total, first.per_page]).toEqual([3, 7, 3]);
    expect(first.results.map((result) => result.id)).toEqual(all.results.slice(0, 3).map((result) => result.id));
    expect(second.results.map((result) => result.id)).toEqual(all.results.slice(3, 6).map((result) => result.id));
    expect(third.results.map((result) => result.id)).toEqual(all.results.slice(6).map((result) => result.id));
    expect(beyond.results).toEqual([]);
    expect(beyond.page).toBe(4);
  });

  it("filters by free text, category and tags", async () => {
    const harness = libraryHarness();
    expect((await search(harness, { type: "hdri", category: "studio" })).results.map((result) => result.id).sort()).toEqual([
      "blocky_photo_studio",
      "blue_photo_studio",
      "brown_photostudio_01",
    ]);
    expect((await search(harness, { type: "hdri", category: "STUDIO", query: "blue" })).results.map((result) => result.id)).toEqual(["blue_photo_studio"]);
    expect((await search(harness, { query: "parking asphalt" })).results.map((result) => result.id)).toEqual(["abandoned_parking"]);
    expect((await search(harness, { type: "hdri", tags: ["parking", "industrial"] })).results.map((result) => result.id)).toEqual(["abandoned_parking"]);
    expect((await search(harness, { type: "hdri", tags: ["parking", "beach"] })).total).toBe(0);
    expect((await search(harness, { type: "model", query: "barrel" })).results.map((result) => [result.id, result.type, result.resolutions])).toEqual([
      ["Barrel_01", "model", ["1k", "2k", "4k", "8k"]],
    ]);
    const everything = await search(harness, { per_page: 24 });
    expect(everything.total).toBe(17);
    expect(new Set(everything.results.map((result) => result.type))).toEqual(new Set(["hdri", "texture", "model"]));
  });

  it("refuses an unknown category with the known ones", async () => {
    const harness = libraryHarness();
    const result = await refused(harness, { type: "hdri", category: "underwater" });
    expect(texts(result)).toMatch(/^refused: "underwater" is not a Poly Haven category for hdri; known categories include natural light, outdoor/);
  });

  it("refuses bad arguments", async () => {
    const harness = libraryHarness();
    expect(texts(await refused(harness, { type: "hdris" }))).toContain("type");
    expect(texts(await refused(harness, { per_page: 25 }))).toContain("per_page");
    expect(texts(await refused(harness, { page: 0 }))).toContain("page");
    expect(texts(await refused(harness, { color: "red" }))).toContain("color");
    expect(harness.polyHaven.seen).toEqual([]);
  });

  it("fails with a clear message when there is no network", async () => {
    const harness = libraryHarness();
    harness.polyHaven.offline = true;
    const result = await refused(harness, { type: "hdri", query: "sky" });
    expect(texts(result)).toBe(
      "offline: Poly Haven is unreachable, cannot reach api.polyhaven.com after 3 attempts (ENOTFOUND: getaddrinfo ENOTFOUND api.polyhaven.com). Search needs the network. Assets already downloaded into library/ still work with library_apply.",
    );
  });

  it("answers again from the disk cache without the network", async () => {
    const harness = libraryHarness();
    const online = await search(harness, { type: "hdri", category: "studio" });
    harness.polyHaven.offline = true;
    const before = harness.polyHaven.seen.length;
    expect(await search(harness, { type: "hdri", category: "studio" })).toEqual(online);
    expect(harness.polyHaven.seen.length).toBe(before);
  });
});
