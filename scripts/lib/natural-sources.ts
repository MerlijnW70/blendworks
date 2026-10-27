import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Library, type BridgeAccess } from "../../src/mcp/library/index.js";
import { Workspace } from "../../src/mcp/workspace.js";
import type { NaturalClass } from "../../src/judge/natural-spec.js";
import { startSession } from "../../src/session.js";
import { RESOLUTION, SCANS } from "./natural-calibration.js";
import type { CalibrationInput, Exclusive } from "./natural-calibration-run.js";
import type { ProceduralRecord } from "./natural-calibration-doc.js";

const NO_BRIDGE: BridgeAccess = { commands: [], request: () => Promise.reject(new Error("the calibration does not use the bridge to download")) };

type Downloaded = { main?: string; folder: string };
type LicenceRecord = { source: string; license: string };

export async function downloadScans(workspaceDir: string, log: (line: string) => void, only?: readonly string[]): Promise<CalibrationInput[]> {
  const workspace = Workspace.open(workspaceDir);
  const library = new Library({ workspace });
  const inputs: CalibrationInput[] = [];
  for (const scan of SCANS.filter((entry) => only === undefined || only.includes(entry.id))) {
    const result = await library.call("library_download", { id: scan.id, resolution: RESOLUTION, format: "gltf" }, NO_BRIDGE);
    const text = result.content.map((item) => (item.type === "text" ? item.text : "")).join("\n");
    if (result.isError) throw new Error(`downloading ${scan.id} failed: ${text}`);
    const downloaded = JSON.parse(text) as Downloaded;
    if (downloaded.main === undefined) throw new Error(`${scan.id} has no main file`);
    const record = JSON.parse(readFileSync(join(workspace.root, downloaded.folder, "LICENSE.json"), "utf8")) as LicenceRecord;
    log(`scan ${scan.id}: ${downloaded.main}`);
    inputs.push({ id: scan.id, kind: "scan", classes: [scan.class], path: join(workspace.root, downloaded.main), source: record.source, licence: record.license });
  }
  return inputs;
}

export type Recipe = { id: string; classes: NaturalClass[]; description: string; commands: string[]; steps: { cmd: string; args: Record<string, unknown> }[]; file: string };

const STEP_TIMEOUT_MS = 600_000;

type Step = { cmd: string; args: Record<string, unknown> };

const EXAMPLE_LAYERS: Record<string, unknown>[] = [
  { amplitude: 0.45, seed: 3, mode: "billow", scale: 2.6, octaves: 3, hurst: 0.9 },
  { amplitude: 0.2, seed: 5, basis: "worley_f2_minus_f1", mode: "ridged", ridge_offset: 0.7, scale: 1.1, octaves: 3, hurst: 0.6, warp: 0.2, warp_octaves: 2 },
  { amplitude: 0.03, seed: 8, scale: 0.3, octaves: 3, hurst: 0.5 },
];

function noiseRock(id: string, layers: Record<string, unknown>[], description: string): Recipe {
  const name = id.replace(/-/g, "_");
  const steps: Step[] = [
    { cmd: "new_scene", args: {} },
    { cmd: "add_primitive", args: { type: "ico_sphere", name, radius: 1.6, subdivisions: 6 } },
    { cmd: "transform", args: { name, scale: [1.35, 1.0, 0.8] } },
    { cmd: "apply_transform", args: { name, scale: true } },
    ...layers.map((layer) => ({ cmd: "noise_displace", args: { name, ...layer } })),
    { cmd: "shade_smooth", args: { name } },
    { cmd: "uv_smart_project", args: { name, island_margin: 0.01 } },
    { cmd: "material_procedural", args: { name: "boulder", stone: { color: [0.4, 0.38, 0.35], cracks: false } } },
    { cmd: "assign_material", args: { name, material: "boulder" } },
    { cmd: "bake", args: { names: [name], channels: ["base_color"], size: 512, rewire: true, device: "cpu" } },
    { cmd: "export", args: { path: `${id}.glb`, names: [name] } },
  ];
  return { id, classes: ["rock"], description, commands: [...new Set(steps.map((step) => step.cmd))], steps, file: `${id}.glb` };
}

export const PROCEDURAL: readonly Recipe[] = [
  noiseRock("noise-rock-example", EXAMPLE_LAYERS, "the rock of docs/examples/noise_terrain.py: billow, warped ridged Worley and fine fBm layers on a 6-subdivision ico sphere, base colour baked from the boulder stone material"),
  noiseRock("noise-rock-billow", EXAMPLE_LAYERS.slice(0, 1), "the example's first layer alone: billow perlin, 3 octaves"),
  noiseRock("noise-rock-ridged", [{ amplitude: 0.4, seed: 12, basis: "worley_f2_minus_f1", mode: "ridged", ridge_offset: 0.7, scale: 1.4, octaves: 5, hurst: 0.6 }], "one ridged Worley layer, 5 octaves"),
  noiseRock("noise-rock-fine", [...EXAMPLE_LAYERS, { amplitude: 0.015, seed: 21, scale: 0.08, octaves: 3, hurst: 0.5 }], "the example with a fourth, 8 cm fBm layer"),
];

export function plannedRecipes(available: ReadonlySet<string>): { build: Recipe[]; skipped: ProceduralRecord[] } {
  const build: Recipe[] = [];
  const skipped: ProceduralRecord[] = [];
  for (const recipe of PROCEDURAL) {
    const missing = recipe.commands.filter((command) => !available.has(command));
    if (missing.length === 0) build.push(recipe);
    else skipped.push({ id: recipe.id, status: "skipped", reason: `the bridge on this main has no ${missing.join(", ")}` });
  }
  return { build, skipped };
}

function commandNames(described: Record<string, unknown>): Set<string> {
  const commands = Array.isArray(described["commands"]) ? (described["commands"] as { name?: unknown }[]) : [];
  return new Set(commands.flatMap((entry) => (typeof entry.name === "string" ? [entry.name] : [])));
}

export async function buildProcedural(workspaceDir: string, exclusive: Exclusive, log: (line: string) => void): Promise<{ inputs: CalibrationInput[]; records: ProceduralRecord[] }> {
  mkdirSync(workspaceDir, { recursive: true });
  return exclusive(async () => {
    const session = await startSession({ workspace: workspaceDir, autosaveSeconds: "off" });
    try {
      const { build, skipped } = plannedRecipes(commandNames(await session.call("describe", {})));
      const inputs: CalibrationInput[] = [];
      log(`procedural: building ${build.map((recipe) => recipe.id).join(", ") || "nothing"}`);
      const records: ProceduralRecord[] = [...skipped];
      for (const recipe of build) {
        for (const step of recipe.steps) await session.call(step.cmd, step.args, { timeoutMs: STEP_TIMEOUT_MS });
        inputs.push({ id: recipe.id, kind: "procedural", classes: recipe.classes, path: join(workspaceDir, recipe.file), source: `scripts/lib/natural-sources.ts: ${recipe.description}`, licence: "generated" });
        records.push({ id: recipe.id, status: "built", reason: null });
      }
      for (const record of skipped) log(`procedural ${record.id}: skipped, ${record.reason}`);
      return { inputs, records };
    } finally {
      await session.close();
    }
  });
}
