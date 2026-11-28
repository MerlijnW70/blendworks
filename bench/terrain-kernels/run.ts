import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { checkedBlender } from "../../scripts/lib/blender-check.js";
import { buildNative } from "../../scripts/lib/native-build.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "../../scripts/lib/paths.js";
import { runBlender } from "../../scripts/lib/run.js";
import { benchTable, recordTable, type BenchResult } from "./table.js";

const args = process.argv.slice(2);
const option = (name: string, fallback: string): string => {
  const index = args.indexOf(name);
  return index >= 0 && index + 1 < args.length ? (args[index + 1] as string) : fallback;
};
const size = option("--size", "2049");
const repeats = option("--repeats", "3");
const built = buildNative();
if (!built.ok) {
  console.error(built.output);
  process.exit(1);
}
const root = ensureCacheRoot(cacheRoot());
const folder = join(root, "bench-terrain");
mkdirSync(folder, { recursive: true });
const output = join(folder, `bench-${size}.json`);
const blender = checkedBlender(root);
const script = join(repoRoot, "bench", "terrain-kernels", "bench.py");
const run = await runBlender(blender.path, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", script, "--", output, size, repeats], { root, label: "bench-terrain", timeoutMs: 60 * 60 * 1000 });
if (run.code !== 0) {
  console.error(run.stdout.slice(-4000), run.stderr.slice(-4000));
  process.exit(1);
}
const result = JSON.parse(readFileSync(output, "utf8")) as BenchResult;
const table = benchTable(result);
console.log(table);
if (args.includes("--record")) {
  const doc = join(repoRoot, "docs", "terrain-core.md");
  writeFileSync(doc, recordTable(readFileSync(doc, "utf8"), table));
  console.log(`recorded in ${doc}`);
}
const failed = result.rows.filter((row) => !row.pass).map((row) => row.kernel);
if (failed.length > 0) {
  console.error(`targets missed: ${failed.join(", ")}`);
  process.exit(1);
}
console.log("every target holds");
