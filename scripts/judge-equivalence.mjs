import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { blenderJobs } from "../src/blender.js";
import { judge } from "../src/judge/run.js";
import { differences, equivalenceCases, judgeCase, verdictAndValues } from "./lib/equivalence.js";
import { ensureFixtures } from "./lib/fixtures.js";
import { cacheRoot, repoRoot } from "./lib/paths.js";

const BASELINE = join(repoRoot, "test", "judge", "equivalence", "fixtures.json");
const USAGE = `usage: npm run equivalence -- fixtures [--record] [--baseline file] [--only text]
       npm run equivalence -- compare <before dir> <after dir>

fixtures judges every judge fixture with a spec that turns on every rule group, and compares the
rules, measured values and verdict with the stored reports of the previous judge (--record stores them).
compare reads <name>/report.json in both folders and compares the same parts, apart from timings.`;

function option(args, name, fallback) {
  const index = args.indexOf(name);
  return index === -1 ? fallback : args[index + 1];
}

async function pool(items, limit, work) {
  const results = new Array(items.length);
  let next = 0;
  const lane = async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await work(items[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, lane));
  return results;
}

async function fixtures(args) {
  const baselinePath = resolve(option(args, "--baseline", BASELINE));
  const only = option(args, "--only", "");
  const folders = await ensureFixtures();
  const cases = equivalenceCases(folders).filter((entry) => entry.id.includes(only));
  const work = join(cacheRoot(), "equivalence");
  rmSync(work, { recursive: true, force: true });
  const started = performance.now();
  const results = await pool(cases, blenderJobs(), async (entry) => {
    const caseStarted = performance.now();
    const value = await judgeCase(judge, entry, folders, work);
    return { id: entry.id, value, seconds: (performance.now() - caseStarted) / 1000 };
  });
  const wall = ((performance.now() - started) / 1000).toFixed(1);
  if (args.includes("--record")) {
    mkdirSync(dirname(baselinePath), { recursive: true });
    writeFileSync(baselinePath, `{\n${results.map((result) => `${JSON.stringify(result.id)}: ${JSON.stringify(result.value)}`).join(",\n")}\n}\n`);
    console.log(`recorded ${results.length} fixture reports in ${baselinePath} (${wall} s)`);
    return 0;
  }
  const baseline = JSON.parse(readFileSync(baselinePath, "utf8"));
  let different = 0;
  for (const result of results) {
    const found = differences(baseline[result.id], result.value);
    if (found.length > 0) different += 1;
    console.log(`${found.length === 0 ? "same     " : "DIFFERENT"} ${result.id} (${result.seconds.toFixed(1)} s)`);
    for (const line of found.slice(0, 10)) console.log(`    ${line}`);
  }
  console.log(`${results.length - different} of ${results.length} fixture reports have the same rules, values and verdict as the stored ones (${wall} s)`);
  return different === 0 ? 0 : 1;
}

function compare(args) {
  const [before, after] = args.map((path) => resolve(path));
  if (before === undefined || after === undefined) {
    console.error(USAGE);
    return 2;
  }
  let different = 0;
  const names = readdirSync(before).filter((name) => existsSync(join(before, name, "report.json")) && existsSync(join(after, name, "report.json")));
  for (const name of names.sort()) {
    const first = JSON.parse(readFileSync(join(before, name, "report.json"), "utf8"));
    const second = JSON.parse(readFileSync(join(after, name, "report.json"), "utf8"));
    const found = differences(verdictAndValues(first, [join(before, name)]), verdictAndValues(second, [join(after, name)]));
    if (found.length > 0) different += 1;
    const speed = first.timings.total / Math.max(second.timings.total, 0.001);
    console.log(`${found.length === 0 ? "same     " : "DIFFERENT"} ${name}: judge ${first.timings.total.toFixed(2)} s before, ${second.timings.total.toFixed(2)} s after (${speed.toFixed(2)} x)`);
    for (const line of found.slice(0, 10)) console.log(`    ${line}`);
  }
  console.log(`${names.length - different} of ${names.length} reports have the same rules, values and verdict`);
  return different === 0 && names.length > 0 ? 0 : 1;
}

const [command, ...rest] = process.argv.slice(2);
if (command === "fixtures") process.exitCode = await fixtures(rest);
else if (command === "compare") process.exitCode = compare(rest);
else {
  console.error(USAGE);
  process.exitCode = 2;
}
