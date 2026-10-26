import { afterEach, describe, expect, it } from "vitest";
import { RUN_PYTHON_WARNING } from "../src/mcp/tools.js";
import { type StartHeadless, startBlendworks } from "../src/mcp/start.js";
import { FakeBridge, PNG_1X1 } from "./mcp-fake-bridge.js";
import { call, type Harness, headlessHarness, scratchDir, texts, unusedPort } from "./mcp-helpers.js";

async function startHeadlessWith(allowPython: boolean, startHeadless: StartHeadless) {
  return startBlendworks({ workspace: scratchDir(), port: await unusedPort(), allowPython, startHeadless });
}

let harness: Harness | undefined;

afterEach(async () => {
  await harness?.close();
  harness = undefined;
});

describe("tools built from the bridge's describe", () => {
  it("names every command blender_<command>, except describe, whose result the list itself is", async () => {
    harness = await headlessHarness();
    const { tools } = await harness.client.listTools();
    expect(tools.map((tool) => tool.name).sort()).toEqual([
      "blender_add_primitive",
      "blender_export",
      "blender_render_preview",
      "blender_scene_info",
      "blender_slow",
    ]);
    const add = tools.find((tool) => tool.name === "blender_add_primitive");
    expect(add?.description).toBe("Add a primitive mesh object.");
  });

  it("converts the bridge schema into a closed JSON schema", async () => {
    harness = await headlessHarness();
    const { tools } = await harness.client.listTools();
    const add = tools.find((tool) => tool.name === "blender_add_primitive");
    expect(add?.inputSchema).toEqual({
      type: "object",
      additionalProperties: false,
      required: ["type"],
      properties: {
        type: { type: "string", description: "Primitive kind.", enum: ["cube", "cylinder", "cone", "sphere", "ico_sphere", "torus", "plane"] },
        size: { type: "number", description: "Size in metres.", exclusiveMinimum: 0, maximum: 1000, default: 2 },
        segments: { type: "integer", description: "Segments around.", minimum: 3, maximum: 256 },
        location: { type: "array", description: "Location in metres.", items: { type: "number", minimum: -1000, maximum: 1000 }, minItems: 3, maxItems: 3 },
      },
    });
    const exporter = tools.find((tool) => tool.name === "blender_export");
    expect(exporter?.inputSchema.required).toEqual(["path"]);
    expect(exporter?.inputSchema.properties?.["path"]).toEqual({ type: "string", description: "File path inside the workspace, relative to it.", minLength: 1, maxLength: 1024 });
  });

  it("passes arguments to the bridge and its result back as text", async () => {
    harness = await headlessHarness();
    const result = await call(harness.client, "blender_add_primitive", { type: "cube", size: 1 });
    expect(result.isError).toBeFalsy();
    expect(JSON.parse(texts(result))).toEqual({ object: "cube.0" });
    expect(harness.bridge.requests.at(-1)).toMatchObject({ cmd: "add_primitive", args: { type: "cube", size: 1 } });
  });

  it("returns bridge refusals as tool errors with their code", async () => {
    harness = await headlessHarness();
    harness.bridge.answer = (request) => ({ id: request.id, ok: false, error: { code: "bad_args", message: "size must be at least 0.001" } });
    const result = await call(harness.client, "blender_add_primitive", { type: "cube", size: 0 });
    expect(result.isError).toBe(true);
    expect(texts(result)).toBe("bad_args: size must be at least 0.001");
  });

  it("refuses a tool the bridge does not offer", async () => {
    harness = await headlessHarness();
    const result = await call(harness.client, "blender_run_python", { code: "print(1)" });
    expect(result.isError).toBe(true);
    expect(harness.bridge.requests.map((request) => request.cmd)).not.toContain("run_python");
  });
});

describe("render_preview", () => {
  it("comes back as PNG image content plus a short text", async () => {
    harness = await headlessHarness();
    const result = await call(harness.client, "blender_render_preview", { views: ["front", "top"] });
    expect(result.isError).toBeFalsy();
    expect(result.content).toEqual([
      { type: "text", text: "Rendered 2 views at 1x1 px with cycles, 8 samples: front, top." },
      { type: "image", data: PNG_1X1, mimeType: "image/png" },
      { type: "image", data: PNG_1X1, mimeType: "image/png" },
    ]);
    expect(Buffer.from(PNG_1X1, "base64").subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  });
});

describe("run_python gating", () => {
  it("is not offered when the bridge lacks it", async () => {
    harness = await headlessHarness({ allowPython: false });
    const { tools } = await harness.client.listTools();
    expect(tools.some((tool) => tool.name === "blender_run_python")).toBe(false);
  });

  it("is offered when the bridge has it, marked as running arbitrary code", async () => {
    harness = await headlessHarness({ allowPython: true });
    const { tools } = await harness.client.listTools();
    const runPython = tools.find((tool) => tool.name === "blender_run_python");
    expect(runPython?.description?.startsWith(RUN_PYTHON_WARNING)).toBe(true);
    expect(runPython?.description).toContain("runs arbitrary Python code");
    expect(runPython?.annotations).toMatchObject({ destructiveHint: true, openWorldHint: true });
  });

  it("passes --allow-python on to the headless session it starts", async () => {
    for (const allowPython of [false, true]) {
      const seen: boolean[] = [];
      const bridge = new FakeBridge({ allowPython });
      const started = await startHeadlessWith(allowPython, async (options) => {
        seen.push(options.allowPython);
        return bridge.link();
      });
      expect(seen).toEqual([allowPython]);
      await started.connection.close();
    }
  });
});

describe("server instructions", () => {
  it("tell the model to work in metres, preview, verify and export", async () => {
    harness = await headlessHarness();
    const instructions = harness.client.getInstructions() ?? "";
    expect(instructions).toContain("metres");
    expect(instructions).toContain("blender_render_preview");
    expect(instructions).toContain("blender_scene_info");
    expect(instructions).toContain("blender_export");
  });
});
