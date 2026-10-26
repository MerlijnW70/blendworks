import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { blenderPath } from "../../src/blender.js";

export const ARTIFACTS = resolve("artifacts", "test-judge");

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

export function writeSpec(dir: string, name: string, overrides: Record<string, unknown> = {}): string {
  const path = join(dir, `${name}.spec.json`);
  writeFileSync(path, JSON.stringify({ ...CRATE_SPEC, ...overrides }, null, 2));
  return path;
}

export function makeFixtures(name: string): { assets: string; markers: string } {
  const assets = freshDir(name, "assets");
  const markers = freshDir(name, "markers");
  execFileSync(
    blenderPath(),
    ["--background", "--factory-startup", "--python-exit-code", "1", "--python", resolve("test", "judge", "fixtures.py"), "--", assets, markers],
    { stdio: "pipe", timeout: 120_000 },
  );
  return { assets, markers };
}
