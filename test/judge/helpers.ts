import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { inject } from "vitest";
import { cacheRoot } from "../../scripts/lib/paths.js";
import { blenderSlotHeld } from "../setup/slot.js";

export const ARTIFACTS = join(cacheRoot(), "test-judge");

export const CRATE_SPEC = {
  name: "wooden crate",
  format: "glb",
  triangles: { max: 800 },
  size: { x: [0.95, 1.05], y: [0.95, 1.05], z: [0.75, 0.85] },
  origin: "bottom-centre",
  manifold: true,
  materials: { min: 1, max: 3 },
  uv: { required: true, maxOverlap: 0.05 },
  objects: { max: 1 },
  fileSize: { maxBytes: 2_000_000 },
  views: ["front", "back", "left", "right", "top", "three-quarter"],
  brief: "A sturdy wooden crate with metal corner brackets, for a top-down game.",
};

export function freshDir(...parts: string[]): string {
  const dir = join(ARTIFACTS, ...parts);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function emptyDirectory(dir: string): void {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
}

export function writeSpec(dir: string, name: string, overrides: Record<string, unknown> = {}): string {
  const path = join(dir, `${name}.spec.json`);
  writeFileSync(path, JSON.stringify({ ...CRATE_SPEC, ...overrides }, null, 2));
  return path;
}

export function makeFixtureSet(set: string, name: string): { assets: string; markers: string } {
  const sets = inject("fixtureSets");
  if (sets === null) throw new Error("the judge fixtures are not available: set BLENDER (see README) and run the tests without BLENDWORKS_FIXTURES=skip");
  const cached = sets[set];
  if (cached === undefined) throw new Error(`no fixture set named ${set}; the sets are ${Object.keys(sets).join(", ")}`);
  if (!blenderSlotHeld()) throw new Error("call useBlenderSlot() at the top of this test file, before anything that starts Blender");
  const assets = freshDir(name, "assets");
  cpSync(cached.assets, assets, { recursive: true });
  return { assets, markers: cached.markers };
}

export function makeFixtures(name: string): { assets: string; markers: string } {
  return makeFixtureSet("fixtures", name);
}

export function makeTextureFixtures(name: string): string {
  return makeFixtureSet("texture_fixtures", name).assets;
}
