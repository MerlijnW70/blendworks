import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { repoRoot } from "./paths.js";

export const BLENDER_MARKER = "useBlenderSlot(";

export type TestSet = { plain: string[]; blender: string[]; bridge: string[] };

export type Selection = { vitest: string[]; bridge: string[]; reasons: string[] };

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
  [/^bridge\/blendworks_bridge\/(commands\/render|device)\.py$/, ["test_render.py"]],
  [/^bridge\/blendworks_bridge\/commands\/run_python\.py$/, ["test_run_python.py"]],
  [/^bridge\/blendworks_bridge\/commands\/scene\.py$/, ["test_scene.py"]],
  [/^bridge\/blendworks_bridge\/(commands\/(uv|uv_pack)|texel)\.py$/, ["test_uv_texel.py"]],
  [/^bridge\/(addon\/.*|session\.py|build_addon\.py|build-addon\.mjs|blendworks_bridge\/transport\.py)$/, ["test_addon.py", "test_smoke.py"]],
  [/^bridge\/blendworks_bridge\/.*\.py$/, CORE_BRIDGE],
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

function importers(helper: string, files: string[]): string[] {
  const stem = basename(helper).replace(/\.(ts|py)$/, "");
  return files.filter((file) => {
    const text = readFileSync(join(repoRoot, file), "utf8");
    return text.includes(`/${stem}.js"`) || text.includes(`./${stem}.js"`);
  });
}

function bridgeImporters(helper: string, tests: string[]): string[] {
  const stem = basename(helper).replace(/\.py$/, "");
  return tests.filter((name) => new RegExp(`^(from|import) ${stem}\\b`, "m").test(readFileSync(join(repoRoot, "bridge", "tests", name), "utf8")));
}

function sourceTests(file: string, all: string[]): string[] {
  const match = /^src\/(.+)\.ts$/.exec(file);
  if (match === null) return [];
  const path = match[1] ?? "";
  const name = basename(path);
  const area = path.split("/")[0] ?? "";
  if (path === "session") return all.filter((test) => /test\/(session|mcp-e2e)\.test\.ts$/.test(test));
  if (path === "blender") return all.filter((test) => /test\/(blender|tooling\/blender-path)\.test\.ts$/.test(test));
  if (area === "judge") {
    const direct = all.filter((test) => test === `test/judge/${name}.test.ts`);
    return direct.length > 0 ? direct : all.filter((test) => test.startsWith("test/judge/"));
  }
  if (path.startsWith("mcp/library/")) {
    const direct = all.filter((test) => test === `test/library-${name}.test.ts`);
    return direct.length > 0 ? direct : all.filter((test) => /^test\/library-/.test(test));
  }
  if (area === "mcp") {
    const direct = all.filter((test) => test === `test/mcp-${name}.test.ts`);
    return direct.length > 0 ? direct : all.filter((test) => /^test\/(mcp|library)-/.test(test));
  }
  return [];
}

export function selectRelated(changed: string[], tests: TestSet): Selection {
  const everyVitest = [...tests.plain, ...tests.blender];
  const picked = new Set<string>();
  const bridge = new Set<string>();
  const reasons: string[] = [];
  const add = (files: string[], why: string, into: Set<string> = picked): void => {
    const fresh = files.filter((file) => !into.has(file));
    for (const file of fresh) into.add(file);
    if (fresh.length > 0) reasons.push(`${why} -> ${fresh.join(", ")}`);
  };
  for (const file of changed) {
    if (/^test\/.*\.test\.ts$/.test(file)) add(everyVitest.filter((test) => test === file), file);
    else if (/^test\/setup\//.test(file) || /^(scripts\/|vitest\.config\.ts$|package\.json$)/.test(file)) add(everyVitest.filter((test) => test.startsWith("test/tooling/")), file);
    else if (/^test\/.*\.ts$/.test(file)) add(importers(file, everyVitest), file);
    else if (/^src\/.*\.ts$/.test(file)) add(sourceTests(file, everyVitest), file);
    else if (/^bridge\/judge\//.test(file)) add(tests.blender.filter((test) => test.startsWith("test/judge/")), file);
    else if (/^schemas\//.test(file)) add(everyVitest.filter((test) => test === "test/judge/spec.test.ts"), file);
    if (/^scripts\/lib\/(bridge|fast)/.test(file) || /^scripts\/bridge-tests/.test(file)) add(tests.bridge.filter((test) => test === "test_smoke.py"), file, bridge);
    if (/^bridge\/tests\/test_.*\.py$/.test(file)) add(tests.bridge.filter((test) => test === basename(file)), file, bridge);
    else if (/^bridge\/tests\/.*\.py$/.test(file)) add(bridgeImporters(file, tests.bridge), file, bridge);
    else if (/^bridge\//.test(file) && !/^bridge\/judge\//.test(file)) {
      const hit = BRIDGE_MODULES.find(([pattern]) => pattern.test(file));
      if (hit !== undefined) add(tests.bridge.filter((test) => hit[1].includes(test)), file, bridge);
    }
  }
  return { vitest: [...new Set([...tests.plain, ...picked])].sort(), bridge: [...bridge].sort(), reasons };
}

function git(args: string[]): string {
  return execFileSync("git", args, { cwd: repoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
}

export function changedFiles(): string[] {
  let base = "HEAD";
  for (const candidate of ["origin/main", "main"]) {
    try {
      base = git(["merge-base", "HEAD", candidate]).trim();
      break;
    } catch {
      continue;
    }
  }
  const tracked = git(["diff", "--name-only", base]).split("\n");
  const untracked = git(["ls-files", "--others", "--exclude-standard"]).split("\n");
  return [...new Set([...tracked, ...untracked].map((file) => file.trim()).filter((file) => file !== ""))].sort();
}
