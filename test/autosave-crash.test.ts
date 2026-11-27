import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { startSession, type Session } from "../src/session.js";
import { useBlenderSlot } from "./setup/slot.js";
import { waitFor } from "./setup/wait-for.js";
import { workBudget } from "./setup/work-clock.js";

useBlenderSlot();

type Step = [string, Record<string, unknown>];

const STEPS: Step[] = [
  ["new_scene", {}],
  ["heightfield", { name: "land", size: [30, 30], resolution: 61, height: 3, seed: 2 }],
  ["material_procedural", { name: "ground", grass_ground: { density: 0.75, dryness: 0.2 } }],
  ["assign_material", { name: "land", material: "ground" }],
  ["grow_tree", { name: "oak", preset: "oak", seed: 11, location: [0, 0, 0], limit: 0 }],
  ["tree_mesh", { name: "oak" }],
  ["tree_leaves", { name: "oak_bark", leaves_name: "oak_leaves", seed: 11, detail: "full" }],
  ["transform", { name: "land", location: [0, 0, -0.5] }],
];
const KILLED = new Set(["grow_tree", "tree_mesh", "tree_leaves"]);
const RUNNING_MS = 300;
const MEASURE = [
  "import bpy, hashlib, numpy",
  "def digest(collection, field, kind, width):",
  "    data = numpy.empty(len(collection) * width, dtype=kind)",
  "    collection.foreach_get(field, data)",
  "    return hashlib.sha256(data.tobytes()).hexdigest()",
  "result = {}",
  "for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name):",
  "    entry = [obj.type, hashlib.sha256(numpy.array(obj.matrix_world, dtype=numpy.float64).tobytes()).hexdigest(), [slot.material.name if slot.material else None for slot in obj.material_slots]]",
  "    if obj.type == 'MESH':",
  "        mesh = obj.data",
  "        entry += [digest(mesh.vertices, 'co', numpy.float32, 3), digest(mesh.loops, 'vertex_index', numpy.int32, 1), digest(mesh.polygons, 'loop_start', numpy.int32, 1)]",
  "        entry += [(attribute.name, attribute.domain, attribute.data_type) for attribute in mesh.attributes if not attribute.name.startswith('.')]",
  "    result[obj.name] = entry",
  "result['data'] = {name: sorted(block.name for block in getattr(bpy.data, name)) for name in ('meshes', 'materials', 'node_groups', 'images', 'curves')}",
].join("\n");

let sessions: Session[] = [];
let folders: string[] = [];

function workspace(): string {
  const folder = mkdtempSync(join(tmpdir(), "blendworks-crash-"));
  folders.push(folder);
  return folder;
}

async function open(folder: string, autosaveSeconds: number): Promise<Session> {
  const session = await startSession({ workspace: folder, allowPython: true, autosaveSeconds, timeoutMs: 600_000 });
  sessions.push(session);
  return session;
}

async function measure(session: Session): Promise<unknown> {
  return (await session.call("run_python", { code: MEASURE })) as unknown;
}

async function killDuring(session: Session, step: Step): Promise<void> {
  const barrier = session.call("scene_info", { limit: 1 });
  const running = session.send(step[0], step[1]).then(
    () => "replied",
    () => "stopped",
  );
  await barrier;
  await new Promise((resolve) => setTimeout(resolve, RUNNING_MS));
  if (session.pid === undefined) throw new Error("the session has no process id");
  process.kill(session.pid, "SIGKILL");
  await session.exited;
  expect(await running, `${step[0]} finished before it could be killed`).toBe("stopped");
}

afterEach(async () => {
  await Promise.all(sessions.map((session) => session.kill()));
  for (const folder of folders) rmSync(folder, { recursive: true, force: true });
  sessions = [];
  folders = [];
});

describe("crash recovery from the snapshot and the journal", workBudget(600_000), () => {
  it("reaches the same scene after kill -9 during three different slow commands", async () => {
    const straight = await open(workspace(), 3600);
    for (const [cmd, args] of STEPS) await straight.call(cmd, args);
    const expected = await measure(straight);
    await straight.close();

    const folder = workspace();
    let session = await open(folder, 3600);
    const recoveries: Record<string, unknown>[] = [];
    for (const step of STEPS) {
      if (KILLED.has(step[0])) {
        await killDuring(session, step);
        session = await open(folder, 3600);
        const recovered = (await session.call("recover")) as Record<string, unknown>;
        expect(recovered["restored"]).toBe(true);
        expect(recovered["not_replayed"]).toBeUndefined();
        recoveries.push(recovered);
      }
      await session.call(step[0], step[1]);
    }
    expect(recoveries.map((result) => (result["replayed"] as { requests: number }).requests).some((count) => count > 0)).toBe(true);
    expect(await measure(session)).toEqual(expected);
  });

  it("takes a snapshot once the session is idle", async () => {
    const folder = workspace();
    const session = await open(folder, 0);
    await session.call("add_primitive", { type: "cube", name: "A" });
    const record = (): Record<string, unknown> => JSON.parse(readFileSync(join(folder, ".blendworks", "autosave.json"), "utf8")) as Record<string, unknown>;
    expect(record()["reason"]).toBe("before add_primitive, the first change of this session");
    await waitFor(() => record()["reason"] === "when idle", { timeoutMs: 120_000, description: "an idle snapshot" });
    expect(record()["objects"]).toBe(1);
    const status = (await session.call("scene_info")) as { autosave: { journal: { requests: number } } };
    expect(status.autosave.journal.requests).toBe(0);
  });
});
