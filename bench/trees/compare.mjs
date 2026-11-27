import { readFileSync } from "node:fs";
import { join } from "node:path";

const folder = process.argv[2];
const target = Number(process.argv[3] ?? "1.7");
if (!folder) {
  console.error("usage: node bench/trees/compare.mjs <out folder> [target speedup]");
  process.exit(2);
}
const read = (mode) => JSON.parse(readFileSync(join(folder, `${mode}.json`), "utf8"));
const serial = read("serial");
const parallel = read("parallel");
const same = (key) => JSON.stringify(serial[key]) === JSON.stringify(parallel[key]);
const results = (record) => JSON.stringify(record.trees.map((tree) => tree.results));
const checks = {
  objects: same("objects"),
  materials: same("materials"),
  images: same("images"),
  node_groups: same("node_groups"),
  results: results(serial) === results(parallel),
  no_fallbacks: parallel.report.fallbacks.length === 0,
};
const speedup = serial.wall / parallel.wall;
checks.speedup = speedup >= target;
console.log(JSON.stringify({ serial: serial.wall, parallel: parallel.wall, speedup: Number(speedup.toFixed(3)), target, workers: parallel.report.workers, threads_per_worker: parallel.report.threads_per_worker, cpus: parallel.report.cpus, worker_peak_memory: parallel.report.worker_peak_memory, checks }, null, 1));
process.exit(Object.values(checks).every(Boolean) ? 0 : 1);
