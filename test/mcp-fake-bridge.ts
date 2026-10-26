import { createServer, type Server } from "node:net";
import type { AddressInfo } from "node:net";
import { createInterface } from "node:readline";
import { PassThrough, type Readable, type Writable } from "node:stream";
import { LineLink } from "../src/mcp/line-link.js";
import type { BridgeLink, BridgeRequest } from "../src/mcp/protocol.js";

export const PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==";

export interface FakeOptions {
  allowPython?: boolean;
  hang?: Set<string>;
  crashOn?: Set<string>;
  delayMs?: number;
}

function object(properties: Record<string, unknown>, required: string[] = []): Record<string, unknown> {
  return { type: "object", properties, required, additionalProperties: false };
}

const VIEWS = ["front", "back", "left", "right", "top", "three-quarter"];

const BASE_COMMANDS: Record<string, { description: string; schema: Record<string, unknown>; dangerous?: boolean }> = {
  describe: { description: "List every command with its argument schema and a one-line description.", schema: object({}) },
  scene_info: { description: "Report objects, meshes, materials, cameras, lights, bounds and units.", schema: object({}) },
  add_primitive: {
    description: "Add a primitive mesh object.",
    schema: object(
      {
        type: { type: "string", description: "Primitive kind.", enum: ["cube", "cylinder", "cone", "sphere", "ico_sphere", "torus", "plane"] },
        size: { type: "number", description: "Size in metres.", exclusiveMinimum: 0, maximum: 1000, default: 2 },
        segments: { type: "integer", description: "Segments around.", minimum: 3, maximum: 256 },
        location: { type: "array", description: "Location in metres.", items: { type: "number", minimum: -1000, maximum: 1000 }, minItems: 3, maxItems: 3 },
      },
      ["type"],
    ),
  },
  render_preview: {
    description: "Render PNG previews (base64) of the scene.",
    schema: object({ views: { type: "array", description: "Turntable views.", items: { type: "string", enum: VIEWS }, minItems: 1, maxItems: 6 } }),
  },
  export: {
    description: "Export the scene to a .glb, .fbx or .obj file in the workspace.",
    schema: object(
      {
        path: { type: "string", description: "File path inside the workspace, relative to it.", minLength: 1, maxLength: 1024 },
        format: { type: "string", description: "File format.", enum: ["glb", "fbx", "obj"] },
      },
      ["path"],
    ),
  },
  slow: { description: "Wait before replying.", schema: object({ ms: { type: "integer", description: "Wait in ms.", minimum: 0, maximum: 10000 } }) },
};

const RUN_PYTHON = {
  description: "Run Python code inside Blender.",
  schema: object({ code: { type: "string", description: "Python source.", minLength: 1 } }, ["code"]),
  dangerous: true,
};

export class FakeBridge {
  readonly requests: BridgeRequest[] = [];
  readonly sessions: { close: () => void }[] = [];
  inFlight = 0;
  maxInFlight = 0;
  objects: string[] = [];

  constructor(readonly options: FakeOptions = {}) {}

  commands(): Record<string, { description: string; schema: Record<string, unknown>; dangerous?: boolean }> {
    return this.options.allowPython ? { ...BASE_COMMANDS, run_python: RUN_PYTHON } : { ...BASE_COMMANDS };
  }

  describe(): Record<string, unknown> {
    return { protocol: 1, python: this.options.allowPython ?? false, commands: Object.entries(this.commands()).map(([name, spec]) => ({ name, ...spec })) };
  }

  serve(input: Readable, output: Writable, close: () => void): void {
    this.sessions.push({ close });
    this.objects = [];
    const lines = createInterface({ input, crlfDelay: Infinity });
    lines.on("line", (line) => {
      const request = JSON.parse(line) as BridgeRequest;
      this.requests.push(request);
      if (this.options.crashOn?.has(request.cmd)) {
        close();
        return;
      }
      if (this.options.hang?.has(request.cmd)) return;
      this.inFlight += 1;
      this.maxInFlight = Math.max(this.maxInFlight, this.inFlight);
      const delay = request.cmd === "slow" ? Number(request.args["ms"] ?? 0) : (this.options.delayMs ?? 0);
      setTimeout(() => {
        this.inFlight -= 1;
        output.write(`${JSON.stringify(this.answer(request))}\n`);
      }, delay);
    });
  }

  answer(request: BridgeRequest): Record<string, unknown> {
    const { id, cmd, args } = request;
    if (cmd === "run_python" && !this.options.allowPython) return { id, ok: false, error: { code: "forbidden", message: "run_python is off" } };
    if (!(cmd in this.commands())) return { id, ok: false, error: { code: "not_found", message: `unknown command ${cmd}` } };
    if (cmd === "describe") return { id, ok: true, result: this.describe() };
    if (cmd === "add_primitive") {
      const name = `${String(args["type"])}.${this.objects.length}`;
      this.objects.push(name);
      return { id, ok: true, result: { object: name } };
    }
    if (cmd === "scene_info") return { id, ok: true, result: { objects: this.objects.map((name) => ({ name })) } };
    if (cmd === "render_preview") {
      const views = (args["views"] as string[] | undefined) ?? ["three-quarter"];
      const images = views.map((view) => ({ view, camera: null, width: 1, height: 1, mimeType: "image/png", data: PNG_1X1 }));
      return { id, ok: true, result: { images, engine: "cycles", samples: 8, seed: 0 } };
    }
    if (cmd === "export") return { id, ok: true, result: { path: args["path"], bytes: 1234 } };
    if (cmd === "run_python") return { id, ok: true, result: { stdout: "" } };
    return { id, ok: true, result: {} };
  }

  link(): BridgeLink {
    const toBridge = new PassThrough();
    const fromBridge = new PassThrough();
    const close = () => {
      fromBridge.end();
      toBridge.end();
    };
    this.serve(toBridge, fromBridge, close);
    return new LineLink(fromBridge, toBridge, close);
  }

  async listen(): Promise<{ port: number; server: Server }> {
    const server = createServer((socket) => this.serve(socket, socket, () => socket.destroy()));
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    return { port: (server.address() as AddressInfo).port, server };
  }
}
