import { createHash } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { inflateSync } from "node:zlib";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../src/blender.js";
import { scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { useBlenderSlot } from "./setup/slot.js";
import { withWorkBudget, workBudget } from "./setup/work-clock.js";

useBlenderSlot();

const bridgeMissing = !existsSync(join("bridge", "session.py"));

function rgbe(value: number): Buffer {
  const exponent = Math.floor(Math.log2(value)) + 1;
  const byte = Math.floor((value / 2 ** exponent) * 256);
  return Buffer.from([byte, byte, byte, exponent + 128]);
}

function grey(value: number): Buffer {
  const width = 16;
  const height = 8;
  const header = Buffer.from(`#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y ${height} +X ${width}\n`, "ascii");
  return Buffer.concat([header, ...Array.from({ length: width * height }, () => rgbe(value))]);
}

function placeHdri(workspace: string, id: string, data: Buffer): void {
  const folder = join(workspace, "library", "hdri", id);
  mkdirSync(folder, { recursive: true });
  const file = `${id}_1k.hdr`;
  writeFileSync(join(folder, file), data);
  const url = `https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/${file}`;
  const record = {
    asset: id,
    name: id,
    type: "hdri",
    source: `https://polyhaven.com/a/${id}`,
    license: "CC0-1.0",
    license_url: "https://creativecommons.org/publicdomain/zero/1.0/",
    authors: { Test: "All" },
    resolution: "1k",
    format: "hdr",
    main: file,
    files: [{ path: file, url, bytes: data.length, md5: createHash("md5").update(data).digest("hex") }],
    downloaded_at: "2027-01-15T08:00:00.000Z",
  };
  writeFileSync(join(folder, "LICENSE.json"), JSON.stringify(record));
}

function meanBrightness(png: Buffer): number {
  const width = png.readUInt32BE(16);
  const height = png.readUInt32BE(20);
  expect([png[24], png[25]]).toEqual([8, 2]);
  const chunks: Buffer[] = [];
  for (let at = 8; at < png.length; ) {
    const length = png.readUInt32BE(at);
    if (png.toString("latin1", at + 4, at + 8) === "IDAT") chunks.push(png.subarray(at + 8, at + 8 + length));
    at += length + 12;
  }
  const raw = inflateSync(Buffer.concat(chunks));
  const stride = width * 3;
  const previous = Buffer.alloc(stride);
  let sum = 0;
  for (let row = 0; row < height; row += 1) {
    const filter = raw[row * (stride + 1)];
    const line = Buffer.from(raw.subarray(row * (stride + 1) + 1, (row + 1) * (stride + 1)));
    for (let index = 0; index < stride; index += 1) {
      const left = index >= 3 ? (line[index - 3] as number) : 0;
      const up = previous[index] as number;
      const upLeft = index >= 3 ? (previous[index - 3] as number) : 0;
      const pa = Math.abs(up - upLeft);
      const pb = Math.abs(left - upLeft);
      const pc = Math.abs(left + up - 2 * upLeft);
      const paeth = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
      const add = [0, left, up, Math.floor((left + up) / 2), paeth][filter as number] as number;
      line[index] = ((line[index] as number) + add) & 0xff;
      sum += line[index] as number;
    }
    line.copy(previous);
  }
  return sum / (width * height * 3 * 255);
}

describe.skipIf(bridgeMissing)("library_apply with a real headless Blender", () => {
  const workspace = join(scratchDir(), "workspace");
  let client: Client;

  beforeAll(withWorkBudget(120_000, async () => {
    mkdirSync(workspace, { recursive: true });
    placeHdri(workspace, "dark_sky", grey(0.02));
    placeHdri(workspace, "bright_sky", grey(0.8));
    const env: Record<string, string> = {};
    for (const [key, value] of Object.entries(process.env)) if (value !== undefined) env[key] = value;
    env["BLENDWORKS_PORT"] = String(await unusedPort());
    env["BLENDER"] = blenderPath();
    const transport = new StdioClientTransport({ command: process.execPath, args: ["--import", "tsx", join("src", "mcp", "index.ts"), "--workspace", workspace], env, stderr: "pipe" });
    client = new Client({ name: "library-e2e", version: "0.0.0" });
    await client.connect(transport);
  }));

  afterAll(async () => {
    await client?.close();
  });

  async function tool(name: string, args: Record<string, unknown>): Promise<CallToolResult> {
    const result = (await client.callTool({ name, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
    if (result.isError) throw new Error(`${name} failed: ${texts(result)}`);
    return result;
  }

  async function renderLitBy(id: string): Promise<number> {
    const applied = JSON.parse(texts(await tool("library_apply", { id }))) as { steps: { command: string; result: Record<string, unknown> }[] };
    expect(applied.steps[0]?.command).toBe("blender_set_world_hdri");
    expect(applied.steps[0]?.result).toMatchObject({ path: `library/hdri/${id}/${id}_1k.hdr`, width: 16, height: 8 });
    const preview = await tool("blender_render_preview", { camera: "Cam", resolution: 64, samples: 4 });
    const image = preview.content.find((item) => item.type === "image");
    if (image?.type !== "image") throw new Error("no image");
    return meanBrightness(Buffer.from(image.data, "base64"));
  }

  it("lights a render with a downloaded HDRI, without the network", workBudget(300_000), async () => {
    await tool("blender_add_primitive", { type: "sphere" });
    await tool("blender_add_light", { type: "point", name: "Off", energy: 0 });
    await tool("blender_add_camera", { name: "Cam", location: [0, -4, 0], target: [0, 0, 0] });
    const dark = await renderLitBy("dark_sky");
    const bright = await renderLitBy("bright_sky");
    expect(bright).toBeGreaterThan(dark * 5);
    expect(bright).toBeGreaterThan(0.3);
  });
});
