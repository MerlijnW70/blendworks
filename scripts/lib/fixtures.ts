import { mkdirSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { checkedBlender, type CheckedBlender } from "./blender-check.js";
import { ensureEntry, hashFiles } from "./entry-cache.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";
import { runBlender } from "./run.js";

export const FIXTURE_FOLDER = "fixtures";
const KEY_LENGTH = 16;
export const MAIN_SET = "fixtures";
export const FIXTURE_SCRIPT = /^(fixtures|.+_fixtures)\.py$/;

export type FixtureSet = { name: string; script: string };

export type Fixtures = { dir: string; assets: string; markers: string; generated: boolean };

export function fixtureSets(base: string = repoRoot): FixtureSet[] {
  const folder = join(base, "test", "judge");
  return readdirSync(folder)
    .filter((name) => FIXTURE_SCRIPT.test(name))
    .sort()
    .map((name) => ({ name: basename(name, ".py"), script: join(folder, name) }));
}

export function fixtureKey(script: string, blenderVersion: string): string {
  return hashFiles([script], [`blender:${blenderVersion}`]).slice(0, KEY_LENGTH);
}

export async function ensureFixtureSet(root: string, blender: CheckedBlender, set: FixtureSet): Promise<Fixtures> {
  const entry = await ensureEntry({
    root,
    name: `${FIXTURE_FOLDER}/${set.name}`,
    key: fixtureKey(set.script, blender.version),
    generate: async (workDir, finalDir) => {
      const assets = join(workDir, "assets");
      mkdirSync(assets, { recursive: true });
      mkdirSync(join(workDir, "markers"), { recursive: true });
      const args = ["--background", "--factory-startup", "--python-exit-code", "1", "--python", set.script, "--", assets, join(finalDir, "markers")];
      const result = await runBlender(blender.path, args, { root, timeoutMs: 180_000 });
      if (result.code !== 0) throw new Error(`generating the ${set.name} fixtures failed (exit ${result.code})\n${result.stdout.slice(-2000)}\n${result.stderr.slice(-2000)}`);
    },
  });
  return { dir: entry.dir, assets: join(entry.dir, "assets"), markers: join(entry.dir, "markers"), generated: entry.generated };
}

export async function ensureFixtures(root: string = cacheRoot()): Promise<Record<string, Fixtures>> {
  ensureCacheRoot(root);
  const blender = checkedBlender(root);
  const out: Record<string, Fixtures> = {};
  for (const set of fixtureSets()) out[set.name] = await ensureFixtureSet(root, blender, set);
  return out;
}
