import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { buildMap, currentMap, MAP_PATH, MAX_MAP_BYTES, tooLarge } from "./lib/codemap.js";
import { repoRoot } from "./lib/paths.js";

const map = buildMap();
if (tooLarge(map)) {
  console.error(`${MAP_PATH} would be over ${MAX_MAP_BYTES} bytes`);
  process.exit(1);
}
if (process.argv.includes("--check")) {
  if (currentMap() !== map) {
    console.error(`${MAP_PATH} is stale: run npx tsx scripts/codemap.mjs`);
    process.exitCode = 1;
  }
} else {
  writeFileSync(join(repoRoot, MAP_PATH), map);
  console.log(`${MAP_PATH}: ${Buffer.byteLength(map)} bytes`);
}
