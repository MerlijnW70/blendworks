import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { NATURAL_CLASSES } from "../src/judge/natural-spec.js";
import { checkedBlender } from "./lib/blender-check.js";
import { ensureFixtureSet } from "./lib/fixtures.js";
import { MIN_PER_CLASS, RESOLUTION } from "./lib/natural-calibration.js";
import type { ProceduralRecord } from "./lib/natural-calibration-doc.js";
import { runCalibration, standInInputs, verifyDefaults, writeCalibration, type CalibrationInput, type Exclusive } from "./lib/natural-calibration-run.js";
import { buildProcedural, downloadScans } from "./lib/natural-sources.js";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./lib/paths.js";
import { withSlot } from "./lib/slots.js";

const VERIFY_SCANS = ["rock_09", "namaqualand_boulder_02"];
const VERIFY_STAND_INS = ["clouds-ico", "jittered-ico"];

const USAGE = `usage: npm run calibrate:natural -- [--offline <scans.json>] [--json <file>] [--doc <file>] [--defaults <file>] [--verify]

Downloads the pinned Poly Haven scans into the cache, builds the stand-ins, judges every asset with the natural
rules and writes calibration.json, the percentile and threshold tables in natural-shapes.md and the calibrated
defaults of the judge. --offline reads local scans from a JSON list of { id, class, path } and downloads nothing.
--verify calibrates nothing: it judges ${VERIFY_SCANS.join(" and ")} and the stand-ins ${VERIFY_STAND_INS.join(" and ")} with a rock
spec built from the judge's defaults, and exits 0 when the scans pass and the stand-ins fail.`;

const { values } = parseArgs({
  options: { offline: { type: "string" }, json: { type: "string" }, doc: { type: "string" }, defaults: { type: "string" }, verify: { type: "boolean" }, help: { type: "boolean" } },
  strict: true,
});
if (values.help === true) {
  console.log(USAGE);
  process.exit(0);
}

const root = ensureCacheRoot(cacheRoot());
const folder = join(root, "natural-calibration");
const workDir = join(folder, "judged");
rmSync(workDir, { recursive: true, force: true });
mkdirSync(workDir, { recursive: true });
const exclusive: Exclusive = (task) => withSlot(() => task(), { label: "calibrate:natural" });
const log = (line: string) => console.log(line);

function offlineScans(path: string): CalibrationInput[] {
  const listed = JSON.parse(readFileSync(path, "utf8")) as { id: string; class: (typeof NATURAL_CLASSES)[number]; path: string }[];
  return listed.map((entry) => ({ id: entry.id, kind: "scan", classes: [entry.class], path: resolve(entry.path), source: resolve(entry.path), licence: "local" }));
}

const blender = checkedBlender(root);
const standIns = await ensureFixtureSet(root, blender, { name: "natural_fixtures", script: join(repoRoot, "test", "judge", "natural_fixtures.py") });

if (values.verify === true) {
  const chosen = [...(await downloadScans(join(folder, "workspace"), log, VERIFY_SCANS)), ...standInInputs(standIns.assets).filter((input) => VERIFY_STAND_INS.includes(input.id))];
  const verified = await verifyDefaults(chosen.map((input) => ({ ...input, classes: ["rock"] })), workDir, exclusive);
  for (const entry of verified) console.log(`${entry.passed ? "PASS" : "FAIL"}  ${entry.kind} ${entry.id}: ${entry.rules.filter((rule) => rule.rule.startsWith("natural.")).map((rule) => `${rule.rule} ${rule.pass ? "pass" : "FAIL"} ${JSON.stringify(rule.measured)}`).join("; ")}`);
  const expected = verified.every((entry) => entry.passed === (entry.kind === "scan"));
  console.log(expected ? "the scans pass and the stand-ins fail" : "unexpected: a scan failed or a stand-in passed");
  process.exit(expected ? 0 : 1);
}

const scans = values.offline === undefined ? await downloadScans(join(folder, "workspace"), log) : offlineScans(values.offline);
let procedural: { inputs: CalibrationInput[]; records: ProceduralRecord[] } = { inputs: [], records: [] };
if (values.offline === undefined) procedural = await buildProcedural(join(folder, "procedural"), exclusive, log);

const document = await runCalibration({
  inputs: [...scans, ...standInInputs(standIns.assets), ...procedural.inputs],
  procedural: procedural.records,
  workDir,
  blender: blender.version,
  resolution: RESOLUTION,
  exclusive,
  log,
});

const short = NATURAL_CLASSES.filter((kind) => document.assets.filter((asset) => asset.kind === "scan" && asset.classes.includes(kind) && asset.failure === null).length < MIN_PER_CLASS);
if (values.offline === undefined && short.length > 0) {
  console.error(`fewer than ${MIN_PER_CLASS} measured scans for ${short.join(", ")}; nothing written`);
  process.exit(1);
}

writeCalibration(document, {
  json: resolve(values.json ?? join(repoRoot, "docs", "research", "natural-shapes", "calibration.json")),
  doc: resolve(values.doc ?? join(repoRoot, "docs", "research", "natural-shapes.md")),
  defaults: resolve(values.defaults ?? join(repoRoot, "src", "judge", "natural-defaults.ts")),
});
for (const entry of document.thresholds) {
  console.log(`${entry.class} ${entry.measure}: threshold ${entry.threshold ?? "n/a"}, ${entry.separates ? "separates" : "does not separate"} (scans passing ${entry.realPassShare ?? "n/a"}, stand-ins failing ${entry.standInFailShare ?? "n/a"})`);
}
