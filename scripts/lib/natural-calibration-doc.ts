import { NATURAL_CLASSES, type NaturalClass } from "../../src/judge/natural-spec.js";
import type { TextureRepetition } from "./natural-textures.js";
import { MEASURES, PERCENTILES, percentile, type ClassPercentiles, type Defaults, type MeasuredAsset, type ProceduralScore, type Threshold } from "./natural-calibration.js";

export const DOC_START = "<!-- natural-calibration:start -->";
export const DOC_END = "<!-- natural-calibration:end -->";

export type CalibratedAsset = MeasuredAsset & { source: string; licence: string; setSha256: string | null; natural: unknown; failure: string | null };

export type ProceduralRecord = { id: string; status: "built" | "skipped"; reason: string | null };

export type CalibrationDocument = {
  version: 1;
  blender: string;
  resolution: string;
  thresholdRule: string;
  assets: CalibratedAsset[];
  procedural: ProceduralRecord[];
  percentiles: Record<NaturalClass, ClassPercentiles>;
  thresholds: Threshold[];
  defaults: Defaults;
  proceduralScores: ProceduralScore[];
  textures: TextureRepetition[];
};

export const THRESHOLD_RULE =
  "For a lower limit, take the 5th percentile of the class's scans; for an upper limit, the 95th. When the measured stand-in nearest to the scans lies beyond that percentile by at least the measure's step (0.01 for D, 0.001 for solidity and shares, 0.1 degrees for p90), the threshold is the midpoint between the two, rounded to the step, and the measure separates the class. Otherwise the threshold is the percentile and the measure does not separate the class: a stand-in reaches the scans, or no stand-in has a value. A measure also separates only when at least 90 % of the class's scans have a value, so that no default rests on a minority of the scans. Only separating measures become defaults.";

function cell(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "n/a" : value.toFixed(digits);
}

function share(value: number | null): string {
  return value === null ? "n/a" : `${Math.round(value * 100)} %`;
}

function percentileTable(document: CalibrationDocument): string[] {
  const lines = [`| Class | Measure | n | ${PERCENTILES.map((p) => `P${p}`).join(" | ")} |`, `|---|---|---|${PERCENTILES.map(() => "---").join("|")}|`];
  for (const kind of NATURAL_CLASSES) {
    for (const measure of MEASURES) {
      const entry = document.percentiles[kind][measure.key];
      const values = PERCENTILES.map((p) => cell(entry?.values?.[`p${p}`], measure.digits + 1));
      lines.push(`| ${kind} | ${measure.label} | ${entry?.n ?? 0} | ${values.join(" | ")} |`);
    }
  }
  return lines;
}

function proceduralTable(document: CalibrationDocument): string[] {
  const lines = ["| Procedural asset | Class | Against the defaults | Verdict |", "|---|---|---|---|"];
  for (const score of document.proceduralScores) {
    const limits = score.limits.map((entry) => `${entry.limit.replace("natural.", "")} ${cell(entry.value, 4)} ${entry.pass ? "passes" : "fails"} ${entry.threshold}`).join("; ");
    lines.push(`| ${score.id} | ${score.class} | ${limits || "no default"} | ${score.passes ? "pass" : "fail"} |`);
  }
  return lines;
}

function standInTable(document: CalibrationDocument): string[] {
  const lines = [`| Asset | Stands in for | ${MEASURES.map((measure) => measure.key).join(" | ")} |`, `|---|---|${MEASURES.map(() => "---").join("|")}|`];
  for (const asset of document.assets.filter((entry) => entry.kind !== "scan")) {
    lines.push(`| ${asset.id} (${asset.kind}) | ${asset.classes.join(", ")} | ${MEASURES.map((measure) => cell(asset.values[measure.key], measure.digits + 1)).join(" | ")} |`);
  }
  for (const entry of document.procedural.filter((record) => record.status === "skipped")) lines.push(`| ${entry.id} (procedural) | not built: ${entry.reason} | ${MEASURES.map(() => "").join(" | ")} |`);
  return lines;
}

function thresholdTable(document: CalibrationDocument): string[] {
  const lines = [
    "| Limit | Class | Scans P5 or P95 | Scan range | Nearest stand-in | Threshold | Scans passing | Stand-ins failing | Separates | Default |",
    "|---|---|---|---|---|---|---|---|---|---|",
  ];
  for (const entry of document.thresholds) {
    const measure = MEASURES.find((candidate) => candidate.key === entry.measure)!;
    const limit = `natural.${measure.rule}.${measure.limit}`;
    const range = entry.realRange === null ? "n/a" : `${cell(entry.realRange[0], measure.digits + 1)}–${cell(entry.realRange[1], measure.digits + 1)}`;
    const nearest = entry.worstStandIn === null ? (entry.standIns === 0 ? "none" : "no value") : cell(entry.worstStandIn, measure.digits + 1);
    const chosen = document.defaults[entry.class][measure.rule]?.[measure.limit];
    const separates = entry.separates ? "yes" : entry.standInsMeasured === 0 ? "no (no stand-in has a value)" : "no";
    lines.push(
      `| \`${limit}\` | ${entry.class} | ${cell(entry.realP5, measure.digits + 1)} | ${range} | ${nearest} | ${cell(entry.threshold, measure.digits + 1)} | ${share(entry.realPassShare)} | ${share(entry.standInFailShare)} | ${separates} | ${chosen === undefined ? "none" : String(chosen)} |`,
    );
  }
  return lines;
}

function textureTable(document: CalibrationDocument): string[] {
  if (document.textures.length === 0) return ["No texture images were read on this run."];
  const lines = ["| Class | Images | Untiled: range | Untiled: P95 | Tiled 2 x 2: lowest |", "|---|---|---|---|---|"];
  for (const kind of NATURAL_CLASSES) {
    const entries = document.textures.filter((entry) => entry.class === kind);
    const untiled = entries.map((entry) => entry.untiled).filter((value): value is number => value !== null);
    const tiled = entries.map((entry) => entry.tiled).filter((value): value is number => value !== null);
    if (untiled.length === 0) continue;
    lines.push(`| ${kind} | ${entries.length} | ${cell(Math.min(...untiled))}–${cell(Math.max(...untiled))} | ${cell(percentile(untiled, 95))} | ${tiled.length === 0 ? "n/a" : cell(Math.min(...tiled))} |`);
  }
  return lines;
}

export function calibrationMarkdown(document: CalibrationDocument): string {
  const scans = document.assets.filter((asset) => asset.kind === "scan");
  const counts = NATURAL_CLASSES.map((kind) => `${scans.filter((asset) => asset.classes.includes(kind)).length} ${kind}`).join(", ");
  return [
    DOC_START,
    "",
    `Measured by \`npm run calibrate:natural\` in Blender ${document.blender} on ${scans.length} Poly Haven scans at ${document.resolution} (${counts}), ${document.assets.filter((asset) => asset.kind === "stand-in").length} primitive stand-ins and ${document.assets.filter((asset) => asset.kind === "procedural").length} procedural assets. Every value per asset is in \`natural-shapes/calibration.json\`.`,
    "",
    "**Percentiles of the scans per class.**",
    "",
    ...percentileTable(document),
    "",
    "**Stand-ins.**",
    "",
    ...standInTable(document),
    "",
    `**Thresholds and separation.** ${document.thresholdRule}`,
    "",
    ...thresholdTable(document),
    "",
    "**Repetition of the scans' base-colour textures.** The same measure as `natural.repetition`, on the luminance of each base-colour image of each scan (scaled to at most 512 px), untiled and tiled 2 x 2. It is not a rule input; it shows how far untiled scan textures lie from exact tiling.",
    "",
    ...textureTable(document),
    "",
    "**Procedural assets against the defaults.** They are a third group: measured and listed with the stand-ins above, but not used to set any threshold.",
    "",
    ...proceduralTable(document),
    "",
    DOC_END,
  ].join("\n");
}

export function replaceCalibration(markdown: string, block: string): string {
  const start = markdown.indexOf(DOC_START);
  const end = markdown.indexOf(DOC_END);
  if (start < 0 || end < start) throw new Error(`the document has no ${DOC_START} … ${DOC_END} block to replace`);
  return `${markdown.slice(0, start)}${block}${markdown.slice(end + DOC_END.length)}`;
}
