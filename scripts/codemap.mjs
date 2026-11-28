import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { buildMaps, currentMaps, sizeProblems, staleMaps } from "./lib/codemap.js";
import { repoRoot } from "./lib/paths.js";

const maps = buildMaps();
const problems = sizeProblems(maps);
for (const problem of problems) console.error(problem);
if (problems.length > 0) process.exit(1);
const current = currentMaps();
const stale = staleMaps(maps, current);
if (process.argv.includes("--check")) {
  if (stale.length > 0) {
    console.error(`stale maps (run npx tsx scripts/codemap.mjs): ${stale.join(", ")}`);
    process.exitCode = 1;
  }
} else {
  for (const path of stale) {
    const file = join(repoRoot, path);
    if (maps[path] === undefined) rmSync(file);
    else {
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, maps[path]);
    }
  }
  for (const [path, text] of Object.entries(maps)) console.log(`${path}: ${Buffer.byteLength(text)} bytes`);
}
