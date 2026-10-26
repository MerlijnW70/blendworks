import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { type BridgeAccess, Library } from "../src/mcp/library/index.js";
import { Workspace } from "../src/mcp/workspace.js";
import { scratchDir, texts } from "./mcp-helpers.js";

const live = process.env["BLENDWORKS_LIVE"] === "1";
const NO_BRIDGE: BridgeAccess = { commands: [], request: () => Promise.reject(new Error("the bridge is not used")) };

interface Downloaded {
  folder: string;
  resolution: string;
  files: { path: string; bytes: number }[];
}

describe.skipIf(!live)("the Poly Haven library against the live API (BLENDWORKS_LIVE=1)", () => {
  const workspace = Workspace.open(join(scratchDir(), "workspace"));
  const library = new Library({ workspace });

  async function run(name: string, args: Record<string, unknown>): Promise<string> {
    const result = await library.call(name, args, NO_BRIDGE);
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}`);
    return texts(result);
  }

  async function searchAndDownload(type: string): Promise<Downloaded> {
    const page = JSON.parse(await run("library_search", { type, per_page: 1 })) as { total: number; results: { id: string; resolutions: string[] }[] };
    expect(page.total).toBeGreaterThan(0);
    const first = page.results[0];
    if (first === undefined) throw new Error(`no ${type} found`);
    expect(first.resolutions).toContain("1k");
    const downloaded = JSON.parse(await run("library_download", { id: first.id, resolution: "1k" })) as Downloaded;
    for (const file of downloaded.files) expect(statSync(join(workspace.root, downloaded.folder, file.path)).size).toBe(file.bytes);
    const record = JSON.parse(readFileSync(join(workspace.root, downloaded.folder, "LICENSE.json"), "utf8")) as { asset: string; license: string; source: string };
    expect(record).toMatchObject({ asset: first.id, license: "CC0-1.0", source: `https://polyhaven.com/a/${first.id}` });
    return downloaded;
  }

  it("searches for an HDRI and downloads it at 1K", async () => {
    const hdri = await searchAndDownload("hdri");
    expect(hdri.files).toHaveLength(1);
    expect(hdri.files[0]?.path).toMatch(/_1k\.hdr$/);
  }, 120_000);

  it("downloads a texture set at 1K and previews it", async () => {
    const texture = await searchAndDownload("texture");
    expect(texture.files.length).toBeGreaterThanOrEqual(3);
    const id = texture.folder.split("/").pop() as string;
    const preview = await library.call("library_preview", { id, size: 64 }, NO_BRIDGE);
    expect(preview.content.some((item) => item.type === "image" && item.mimeType === "image/png")).toBe(true);
  }, 120_000);
});
