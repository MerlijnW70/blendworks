import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { spawn } from "node:child_process";
import { blenderPath } from "../src/blender.js";
import { BridgeCommandError, sessionArguments, startSession, type Session } from "../src/session.js";

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

interface Described {
  commands: { name: string; description: string; schema: { type: string; properties: Record<string, unknown> } }[];
}

interface Rendered {
  images: { view: string; mimeType: string; width: number; height: number; data: string }[];
}

let sessions: Session[] = [];
let folders: string[] = [];

function workspace(): string {
  const folder = mkdtempSync(join(tmpdir(), "blendworks-session-"));
  folders.push(folder);
  return folder;
}

async function open(allowPython = false): Promise<Session> {
  const session = await startSession({ workspace: workspace(), allowPython });
  sessions.push(session);
  return session;
}

afterEach(async () => {
  await Promise.all(sessions.map((session) => session.close()));
  for (const folder of folders) rmSync(folder, { recursive: true, force: true });
  sessions = [];
  folders = [];
});

describe("the headless session", () => {
  it("describes, builds a cube, reports it and renders a PNG", async () => {
    const session = await open();
    const described = (await session.call("describe")) as unknown as Described;
    const names = described.commands.map((command) => command.name);
    expect(names).toContain("add_primitive");
    expect(names).toContain("render_preview");
    expect(names).not.toContain("run_python");
    expect(described.commands.every((command) => command.schema.type === "object" && command.description.length > 0)).toBe(true);

    const added = await session.call("add_primitive", { type: "cube", name: "Crate", size: 1 });
    expect(added["name"]).toBe("Crate");

    const info = (await session.call("scene_info")) as { objects: { name: string; mesh: { triangles: number } }[] };
    expect(info.objects.map((object) => [object.name, object.mesh.triangles])).toEqual([["Crate", 12]]);

    const rendered = (await session.call("render_preview", { views: ["front", "three-quarter"], resolution: 64, samples: 2 })) as unknown as Rendered;
    expect(rendered.images.map((image) => image.view)).toEqual(["front", "three-quarter"]);
    for (const image of rendered.images) {
      expect(image.mimeType).toBe("image/png");
      expect([image.width, image.height]).toEqual([64, 64]);
      expect(Buffer.from(image.data, "base64").subarray(0, 8).equals(PNG_SIGNATURE)).toBe(true);
    }

    expect(await session.close()).toEqual({ code: 0, signal: null });
  });

  it("rejects refused commands with their code and keeps serving", async () => {
    const session = await open();
    await expect(session.call("add_primitive", { type: "cube", colour: "red" })).rejects.toMatchObject({ code: "bad_args" });
    const refused = await session.send("export", { path: "../escape.glb" });
    expect(refused).toMatchObject({ ok: false, error: { code: "forbidden" } });
    await expect(session.call("run_python", { code: "result = 1" })).rejects.toBeInstanceOf(BridgeCommandError);
    await expect(session.call("delete", { names: ["Ghost"] })).rejects.toMatchObject({ code: "not_found" });
    expect(await session.call("scene_info")).toMatchObject({ objects: [] });
  });

  it("writes exports into the workspace", async () => {
    const session = await open();
    await session.call("add_primitive", { type: "cube" });
    const exported = await session.call("export", { path: "models/cube.glb" });
    const file = join(session.workspace, "models", "cube.glb");
    expect(existsSync(file)).toBe(true);
    expect(exported["bytes"]).toBe(readFileSync(file).length);
    expect(readFileSync(file).subarray(0, 4).toString("latin1")).toBe("glTF");
  });

  it("offers run_python only with allowPython", async () => {
    const session = await open(true);
    const described = (await session.call("describe")) as unknown as Described;
    expect(described.commands.map((command) => command.name)).toContain("run_python");
    expect(await session.call("run_python", { code: "result = 6 * 7" })).toEqual({ stdout: "", result: 42 });
  });

  it("keeps stdout to protocol lines and exits cleanly at the end of its input", async () => {
    const child = spawn(blenderPath(), sessionArguments(workspace(), false), { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => (stdout += chunk.toString("utf8")));
    child.stderr.on("data", (chunk: Buffer) => (stderr += chunk.toString("utf8")));
    const requests = [
      { id: 1, cmd: "add_primitive", args: { type: "cube" } },
      { id: 2, cmd: "export", args: { path: "cube.fbx" } },
    ];
    child.stdin.end(`${requests.map((request) => JSON.stringify(request)).join("\n")}\nnot json\n`);
    const code = await new Promise<number | null>((resolveExit) => child.once("exit", resolveExit));
    expect(code).toBe(0);
    const lines = stdout
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line) as { id: unknown; ok: boolean });
    expect(lines.map((line) => [line.id, line.ok])).toEqual([[1, true], [2, true], [null, false]]);
    expect(stderr).toContain("Blender");
  });
});
