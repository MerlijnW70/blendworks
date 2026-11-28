import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { repoRoot } from "./paths.js";

export const BLENDER_MARKER = "useBlenderSlot(";

export type TestSet = { plain: string[]; blender: string[]; bridge: string[] };

const CORE_BRIDGE = ["test_smoke.py", "test_describe.py", "test_crate.py", "test_scene.py"];

export const BRIDGE_MODULES: [RegExp, string[]][] = [
  [/^bridge\/blendworks_bridge\/(commands\/)?(bake|baking)\.py$/, ["test_bake.py", "test_bake_failures.py", "test_textured_prop.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/)?(files|workspace)\.py$/, ["test_files.py"]],
  [/^bridge\/blendworks_bridge\/commands\/geometry\.py$/, ["test_geometry.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/)?(images|image_header)\.py$/, ["test_images.py"]],
  [/^bridge\/blendworks_bridge\/commands\/lights\.py$/, ["test_lights.py", "test_world_hdri.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/)?(materials|materials_info|nodes)\.py$/, ["test_materials.py", "test_pbr.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/mesh_edit|operators|transaction)\.py$/, ["test_mesh_edit.py"]],
  [/^bridge\/blendworks_bridge\/commands\/modifiers\.py$/, ["test_modifiers.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/(objects|transforms)|selection|rig)\.py$/, ["test_objects.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/)?pbr\.py$/, ["test_pbr.py", "test_textured_prop.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/)?procedural\.py$/, ["test_procedural.py"]],
  [/^bridge\/blendworks_bridge\/(analytic_paths|lofting|paths|revolve|skin|shading|uvlayout|builder|commands\/shapes)\.py$/, ["test_sweep.py", "test_sweep_analytic.py", "test_sweep_closed.py", "test_loft.py", "test_lathe.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/solids|extrusion|gears|chain)\.py$/, ["test_outline_solids.py", "test_roller_chain.py"]],
  [/^bridge\/blendworks_bridge\/(blendfile|exporting|gltf_extras|policy)\.py$/, ["test_files.py", "test_autosave.py", "test_checkpoints.py", "test_export_hierarchy.py"]],
  [/^bridge\/blendworks_bridge\/(copies|instancing|poisson)\.py$/, ["test_instances.py", "test_scatter.py", "test_scatter_options.py"]],
  [/^bridge\/blendworks_bridge\/(cutmarks|slivers|flatfill)\.py$/, ["test_engrave.py", "test_engrave_cutters.py", "test_clean_mesh.py"]],
  [/^bridge\/blendworks_bridge\/(graph_build|graph_read)\.py$/, ["test_material_nodes.py"]],
  [/^bridge\/blendworks_bridge\/inspect_scene\.py$/, ["test_scene_info.py", "test_describe.py"]],
  [/^bridge\/blendworks_bridge\/(masks|occlusion|scratches)\.py$/, ["test_procedural.py", "test_brass.py", "test_scratch_direction.py"]],
  [/^bridge\/blendworks_bridge\/(normals|commands\/mesh_query)\.py$/, ["test_mesh_edit.py", "test_selection_kit.py"]],
  [/^bridge\/blendworks_bridge\/(polyhedron)\.py$/, ["test_fracture.py", "test_chip.py"]],
  [/^bridge\/blendworks_bridge\/commands\/blob\.py$/, ["test_remesh_blob.py"]],
  [/^bridge\/blendworks_bridge\/(handler|__init__|commands\/__init__)\.py$/, CORE_BRIDGE],
  [/^bridge\/blendworks_bridge\/(commands\/render|device)\.py$/, ["test_render.py"]],
  [/^bridge\/blendworks_bridge\/commands\/run_python\.py$/, ["test_run_python.py"]],
  [/^bridge\/blendworks_bridge\/commands\/scene\.py$/, ["test_scene.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/(uv|uv_pack)|texel)\.py$/, ["test_uv_texel.py"]],
  [/^bridge\/(addon\/.*|session\.py|build_addon\.py|build-addon\.mjs|blendworks_bridge\/transport\.py)$/, ["test_addon.py", "test_smoke.py"]],
  [/^bridge\/(package\/.*|blendworks_bridge\/commands\/lods)\.py$/, ["test_lods.py", "test_package_math.py"]],
];

export const BRIDGE_FALLBACK: [RegExp, string[]][] = [[/^bridge\/blendworks_bridge\/.*\.py$/, CORE_BRIDGE]];

export const EXAMPLE_AREAS: [RegExp, string][] = [
  [/(^|\/)(tree|trees)(_[a-z]+)?\.(py|ts)$/, "tree"],
  [/(^|\/)lsystem(_[a-z]+)?\.(py|ts)$/, "lsystem"],
  [/(^|\/)scatter(_[a-z]+)?\.(py|ts)$/, "scatter"],
  [/(^|\/)shells?(_[a-z]+)?\.(py|ts)$/, "shells"],
  [/(^|\/)phyllotaxis(_[a-z]+)?\.(py|ts)$/, "phyllotaxis"],
  [/(^|\/)(erosion_[a-z]+|erode|heightgrid|heightfield)\.(py|ts)$/, "eroded-terrain"],
  [/(^|\/)(noise(_[a-z]+)?|noise_displace|terrain)\.(py|ts)$/, "noise-terrain"],
  [/(^|\/)(abrasion|abrade|fracturing|fracture|fragments|chip|blob|remesh)\.(py|ts)$/, "rocks"],
];

function listTests(directory: string, prefix: string): string[] {
  const folder = join(repoRoot, directory);
  if (!existsSync(folder)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = `${prefix}${entry.name}`;
    if (entry.isDirectory()) out.push(...listTests(`${directory}/${entry.name}`, `${path}/`));
    else if (entry.name.endsWith(".test.ts")) out.push(path);
  }
  return out.sort();
}

export function discoverTests(): TestSet {
  const all = listTests("test", "test/");
  const blender = all.filter((file) => readFileSync(join(repoRoot, file), "utf8").includes(BLENDER_MARKER));
  const bridgeFolder = join(repoRoot, "bridge", "tests");
  const bridge = existsSync(bridgeFolder) ? readdirSync(bridgeFolder).filter((name) => /^test_.*\.py$/.test(name)).sort() : [];
  return { plain: all.filter((file) => !blender.includes(file)), blender, bridge };
}

export type BridgeMapping = { tests: string[]; how: "table" | "convention" | "family" | "claimed" | "example" | "none" };

function claimingTests(stem: string, tests: string[], folder: string): string[] {
  const claim = new RegExp(String.raw`^\s*from blendworks_bridge(?:\.commands)?(?:\.${stem}\b| import [^\n]*\b${stem}\b)`, "m");
  return tests.filter((name) => claim.test(readFileSync(join(folder, name), "utf8")));
}

export function bridgeModuleTests(file: string, tests: string[], folder: string = join(repoRoot, "bridge", "tests")): BridgeMapping {
  const override = BRIDGE_MODULES.find(([pattern]) => pattern.test(file));
  if (override !== undefined) return { tests: tests.filter((name) => override[1].includes(name)), how: "table" };
  const stem = basename(file).replace(/\.py$/, "");
  const named = tests.filter((name) => name.startsWith(`test_${stem}`));
  const claimed = claimingTests(stem, tests, folder);
  const together = [...new Set([...named, ...claimed])];
  if (together.length > 0) return { tests: together, how: named.length > 0 ? "convention" : "claimed" };
  const family = stem.split("_")[0] ?? stem;
  const related = tests.filter((name) => name.startsWith(`test_${family}`));
  if (related.length > 0) return { tests: related, how: "family" };
  if (exampleAreas(file).length > 0) return { tests: [], how: "example" };
  const fallback = BRIDGE_FALLBACK.find(([pattern]) => pattern.test(file));
  return { tests: fallback === undefined ? [] : tests.filter((name) => fallback[1].includes(name)), how: "none" };
}

function exampleAreas(file: string): string[] {
  return EXAMPLE_AREAS.filter(([pattern]) => pattern.test(file)).map(([, area]) => `test/${area}-example.test.ts`);
}

export function exampleTests(file: string, all: string[]): string[] {
  const areas = exampleAreas(file);
  return all.filter((test) => areas.includes(test));
}
