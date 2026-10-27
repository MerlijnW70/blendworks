import { rmSync } from "node:fs";
import { join } from "node:path";
import type { Client } from "@modelcontextprotocol/sdk/client/index.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { afterEach, describe, expect, it } from "vitest";
import { startHeadlessSession } from "../src/mcp/headless.js";
import { type Started, startBlendworks } from "../src/mcp/start.js";
import { connectClient, scratchDir, texts, unusedPort } from "./mcp-helpers.js";

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const SLEEP = "import time\ntime.sleep(120)";

interface Live {
  client: Client;
  started: Started;
  workspace: string;
}

let live: Live | undefined;

afterEach(async () => {
  await live?.client.close();
  await live?.started.connection.close();
  live = undefined;
});

async function open(): Promise<Live> {
  const workspace = join(scratchDir(), "workspace");
  const started = await startBlendworks({ workspace, port: await unusedPort(), allowPython: true, startHeadless: (options) => startHeadlessSession(options) });
  return { client: await connectClient(started), started, workspace };
}

async function call(client: Client, name: string, args: Record<string, unknown> = {}): Promise<CallToolResult> {
  return (await client.callTool({ name, arguments: args }, undefined, { timeout: 240_000 })) as CallToolResult;
}

async function ok(client: Client, name: string, args: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const result = await call(client, name, args);
  if (result.isError) throw new Error(`${name} failed: ${texts(result)}`);
  return JSON.parse(texts(result)) as Record<string, unknown>;
}

async function objectNames(client: Client): Promise<string[]> {
  const info = (await ok(client, "blender_scene_info", { detail: "objects" })) as { objects: { name: string }[] };
  return info.objects.map((entry) => entry.name);
}

async function buildPart(client: Client): Promise<number> {
  await ok(client, "blender_add_primitive", { type: "cube", name: "Body", size: 1 });
  await ok(client, "blender_add_primitive", { type: "cylinder", name: "Knob", radius: 0.15, depth: 0.3, location: [0, -0.6, 0.2], rotation: [90, 0, 0] });
  await ok(client, "blender_add_material", { name: "Brass", base_color: [0.8, 0.6, 0.2], metallic: 1 });
  await ok(client, "blender_assign_material", { name: "Knob", material: "Brass" });
  const pid = await ok(client, "blender_run_python", { code: "import os\nresult = os.getpid()" });
  return pid["result"] as number;
}

async function killDuringRunPython(session: Live, pid: number, beforeKill: () => void = () => undefined): Promise<CallToolResult> {
  const pending = call(session.client, "blender_run_python", { code: SLEEP });
  await new Promise((resolve) => setTimeout(resolve, 1500));
  beforeKill();
  process.kill(pid);
  return pending;
}

describe("a real headless session through the MCP server", () => {
  it("reloads the autosave when Blender is killed in the middle of run_python, and says so", async () => {
    live = await open();
    const pid = await buildPart(live.client);
    const crashed = await killDuringRunPython(live, pid);
    expect(crashed.isError).toBe(true);
    expect(texts(crashed)).toMatch(
      /^crashed: Blender stopped while running run_python \(.+\)\. Restarted it\. Reloaded \.blendworks\/autosave\.blend saved at \S+Z \(before run_python\); the scene has 2 objects\./,
    );
    expect(await objectNames(live.client)).toEqual(["Body", "Knob"]);

    for (const shading of ["clay", "wireframe"]) {
      const preview = await call(live.client, "blender_render_preview", { focus: { object: "Knob", width: 0.5 }, shading, resolution: 128, samples: 4, device: "cpu" });
      expect(preview.isError).toBeFalsy();
      const image = preview.content.find((item) => item.type === "image");
      expect(image?.type === "image" && Buffer.from(image.data, "base64").subarray(0, 8).equals(PNG_SIGNATURE)).toBe(true);
      expect(texts(preview)).toContain(`${shading} shading`);
      expect(texts(preview)).toContain('"focus":{"centre":[0,-0.6,0.2],"width":0.5');
    }
  }, 300_000);

  it("comes back empty, and says so, when the autosave is gone", async () => {
    live = await open();
    const pid = await buildPart(live.client);
    const workspace = live.workspace;
    const crashed = await killDuringRunPython(live, pid, () => rmSync(join(workspace, ".blendworks"), { recursive: true, force: true }));
    expect(texts(crashed)).toMatch(/Restarted it\. The scene is empty \(there was no autosave yet\), so rebuild it before continuing\.$/);
    expect(await objectNames(live.client)).toEqual([]);
  }, 300_000);

  it("recovers the same way after a timeout and after a cancellation", async () => {
    live = await open();
    await buildPart(live.client);
    const late = await call(live.client, "blender_run_python", { code: SLEEP, timeout_seconds: 3 });
    expect(texts(late)).toMatch(/^timeout: run_python got no reply within 3 s\. Stopped the session\. Restarted it\. Reloaded \.blendworks\/autosave\.blend .*\(before run_python\); the scene has 2 objects\./);
    expect(await objectNames(live.client)).toEqual(["Body", "Knob"]);

    const controller = new AbortController();
    const cancelled = live.client.callTool({ name: "blender_run_python", arguments: { code: SLEEP } }, undefined, { signal: controller.signal, timeout: 240_000 });
    setTimeout(() => controller.abort(), 1500);
    await expect(cancelled).rejects.toThrow(/abort/i);
    expect(await objectNames(live.client)).toEqual(["Body", "Knob"]);
    expect(live.started.connection.restarts).toBe(2);
  }, 300_000);
});
