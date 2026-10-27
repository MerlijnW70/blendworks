import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { basename } from "node:path";
import { fileURLToPath } from "node:url";

export const USAGE_FILE = fileURLToPath(new URL("./usage.json", import.meta.url));

export interface Usage {
  method: string;
  sources: { file: string; sha256: string; calls: number }[];
  counts: Record<string, number>;
}

const CALL = /\bcmd\(\s*"([a-z][a-z0-9_]*)"/g;

export const RAW_BLENDER_CALLS: Record<string, string> = {
  "bpy.ops.wm.read_factory_settings": "new_scene",
  "bpy.data.meshes.new": "mesh_from_data",
  "bpy.data.materials.new": "add_material",
  "bpy.data.images.new": "image_new",
  "bpy.ops.uv.smart_project": "uv_smart_project",
  "bpy.ops.uv.pack_islands": "uv_pack",
  "bpy.ops.object.bake": "bake",
  "bpy.ops.export_scene.gltf": "export",
  "bmesh.ops.create_cube": "add_primitive",
  "bmesh.ops.bevel": "bevel",
  "bmesh.ops.recalc_face_normals": "recalc_normals",
};

function add(counts: Map<string, number>, name: string, count = 1): void {
  counts.set(name, (counts.get(name) ?? 0) + count);
}

export function countCalls(text: string): Map<string, number> {
  const counts = new Map<string, number>();
  for (const match of text.matchAll(CALL)) add(counts, match[1]!);
  for (const [call, command] of Object.entries(RAW_BLENDER_CALLS)) {
    const found = text.split(`${call}(`).length - 1;
    if (found > 0) add(counts, command, found);
  }
  return counts;
}

export function loadUsage(file: string = USAGE_FILE): Usage {
  return JSON.parse(readFileSync(file, "utf8")) as Usage;
}

function main(files: string[]): void {
  const total = new Map<string, number>();
  const sources = files.map((file) => {
    const text = readFileSync(file, "utf8");
    const counts = countCalls(text);
    for (const [name, count] of counts) total.set(name, (total.get(name) ?? 0) + count);
    return { file: basename(file), sha256: createHash("sha256").update(readFileSync(file)).digest("hex"), calls: [...counts.values()].reduce((sum, count) => sum + count, 0) };
  });
  const usage: Usage = {
    method: 'Call sites in the proof-asset build scripts, counted in the source text: cmd("<command>", ...) in the commands-only scripts, and in the raw bpy scripts the Blender calls that a Blendworks command covers (RAW_BLENDER_CALLS).',
    sources,
    counts: Object.fromEntries([...total].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))),
  };
  writeFileSync(USAGE_FILE, `${JSON.stringify(usage, null, 1)}\n`);
  console.log(`wrote ${USAGE_FILE}: ${sources.map((source) => `${source.file} ${source.calls}`).join(", ")}`);
}

if (process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1]) main(process.argv.slice(2));
