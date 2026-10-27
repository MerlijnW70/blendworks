import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { extname, join, sep } from "node:path";
import type { JudgeOptions } from "../../src/judge/run.js";
import type { Report } from "../../src/judge/report.js";
import { maskFrom, maskImage } from "../../src/judge/silhouette.js";
import { encodePng } from "../../src/judge/visual/png.js";

export type FixtureFolders = Record<string, { assets: string }>;

export type EquivalenceCase = {
  id: string;
  set: string;
  asset: string;
  rules: Record<string, unknown>;
  options: Pick<JudgeOptions, "preview" | "renderTimeoutMs" | "renderMaxTriangles">;
};

export type Judge = (options: JudgeOptions) => Promise<Report>;

const JUDGED = new Set(["glb", "gltf", "fbx", "obj", "blend"]);
const GLTF = new Set(["glb", "gltf"]);
const MOTION = new Set(["glb", "gltf", "blend"]);
const MASK_SIZE = 64;
const CRATE = "fixtures/crate.glb";
const TIMING_KEYS = new Set(["seconds"]);

function everyRule(format: string): Record<string, unknown> {
  const rules: Record<string, unknown> = {
    format,
    triangles: { max: 5000, minVisible: 1 },
    size: { x: [0.95, 1.05], y: [0.95, 1.05], z: [0.75, 0.85] },
    origin: "bottom-centre",
    manifold: { required: true, noInverted: true },
    faces: { maxDegenerate: 0, maxDuplicate: 0, maxHiddenRatio: 0.3 },
    shells: { max: 8 },
    materials: { min: 1, max: 3 },
    uv: { required: true, maxOverlap: 0.05, minCoverage: 0.1 },
    objects: { max: 4, named: [{ name: "*", triangles: { max: 5000 } }] },
    fileSize: { maxBytes: 2_000_000 },
    selfContained: true,
    views: ["front"],
    parts: { maxFloating: 0 },
    textures: { required: ["baseColor"], minSize: 16, maxSize: 4096, embedded: true, maxCount: 8, powerOfTwo: true },
    vertexColors: { required: false },
    reference: { views: { front: { mask: "front.png" }, left: { mask: "left.png" } }, minIoU: 0.5, maxBoundaryDistance: 0.1 },
  };
  if (GLTF.has(format)) rules.gltf = { validator: { maxErrors: 0, maxWarnings: 0 } };
  if (MOTION.has(format)) Object.assign(rules, { rig: { required: false }, skin: { normalized: true, restPose: true }, animation: { loop: true } });
  return rules;
}

export function equivalenceCases(folders: FixtureFolders): EquivalenceCase[] {
  const cases: EquivalenceCase[] = [];
  for (const set of Object.keys(folders).sort()) {
    for (const asset of readdirSync(folders[set]!.assets).sort()) {
      const format = extname(asset).slice(1).toLowerCase();
      if (!JUDGED.has(format)) continue;
      cases.push({ id: `${set}/${asset}`, set, asset, rules: everyRule(format), options: {} });
    }
  }
  const crate = cases.find((entry) => entry.id === CRATE);
  if (crate === undefined) return cases;
  const variant = (suffix: string, rules: Record<string, unknown>, options: EquivalenceCase["options"] = {}) => cases.push({ ...crate, id: `${CRATE}#${suffix}`, rules: { ...crate.rules, ...rules }, options });
  variant("preview", {}, { preview: true });
  variant("six-views", { views: ["front", "back", "left", "right", "top", "three-quarter"] });
  variant("render-skipped", {}, { renderMaxTriangles: 1 });
  variant("render-timeout", { renders: { required: true } }, { renderTimeoutMs: 1 });
  variant("reference-bounds", { reference: { views: { front: { mask: "front.png" } }, bounds: { min: [-0.6, -0.6, 0], max: [0.6, 0.6, 0.9] }, minIoU: 0.5 } });
  return cases;
}

function masks(folder: string): Record<string, string> {
  const shapes: Record<string, (x: number, y: number) => boolean> = {
    "front.png": (x, y) => x >= 8 && x < 56 && y >= 14 && y < 50,
    "left.png": (x, y) => (x - 31.5) ** 2 + (y - 31.5) ** 2 < 24 ** 2,
  };
  const pinned: Record<string, string> = {};
  for (const [name, inside] of Object.entries(shapes)) {
    const data = encodePng(maskImage(maskFrom(MASK_SIZE, MASK_SIZE, inside)));
    writeFileSync(join(folder, name), data);
    pinned[name] = createHash("sha256").update(data).digest("hex");
  }
  return pinned;
}

function withMasks(rules: Record<string, unknown>, pinned: Record<string, string>): Record<string, unknown> {
  const reference = rules.reference as { views: Record<string, { mask: string }> } | undefined;
  if (reference === undefined) return rules;
  const views = Object.fromEntries(Object.entries(reference.views).map(([view, entry]) => [view, { ...entry, sha256: pinned[entry.mask] }]));
  return { ...rules, reference: { ...reference, views } };
}

function withoutTimings(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withoutTimings);
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => !TIMING_KEYS.has(key)).map(([key, entry]) => [key, withoutTimings(entry)]));
}

function relativePaths(value: unknown, roots: string[]): unknown {
  if (typeof value === "string") return roots.reduce((text, root) => text.split(root).join("$ROOT"), value).split(sep).join("/");
  if (Array.isArray(value)) return value.map((entry) => relativePaths(entry, roots));
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, relativePaths(entry, roots)]));
}

const DELIVERY_BYTES = "$DELIVERY_BYTES";

function deliveryBytes(report: Report): Pick<Report, "rules" | "measurements"> {
  const bytes = report.asset.setBytes;
  if (bytes === null) return { rules: report.rules, measurements: report.measurements };
  const rules = report.rules.map((rule) => (rule.rule === "fileSize.maxBytes" && rule.measured === bytes ? { ...rule, measured: DELIVERY_BYTES } : rule));
  const measurements = report.measurements !== null && report.measurements.fileBytes === bytes ? { ...report.measurements, fileBytes: DELIVERY_BYTES } : report.measurements;
  return { rules, measurements } as Pick<Report, "rules" | "measurements">;
}

export function verdictAndValues(report: Report, roots: string[]): unknown {
  const reference = report.reference ? { frame: report.reference.frame, views: report.reference.views.map(({ silhouette: _, overlay: __, ...view }) => view) } : (report.reference ?? null);
  const renders = report.renders ? { status: report.renders.status, reason: report.renders.reason, failure: report.renders.failure, viewsSkipped: report.renders.viewsSkipped, views: report.renders.views.map((view) => view.view) } : null;
  const { rules, measurements } = deliveryBytes(report);
  return relativePaths({ passed: report.passed, failure: report.failure, rules, measurements, validation: withoutTimings(report.validation ?? null), reference, renders }, roots);
}

export async function judgeCase(judge: Judge, entry: EquivalenceCase, folders: FixtureFolders, work: string): Promise<unknown> {
  const folder = join(work, entry.id.replace(/[^A-Za-z0-9.-]+/g, "_"));
  mkdirSync(folder, { recursive: true });
  const spec = join(folder, "spec.json");
  writeFileSync(spec, JSON.stringify({ name: entry.id, ...withMasks(entry.rules, masks(folder)) }, null, 2));
  const assets = folders[entry.set]!.assets;
  const report = await judge({ specPath: spec, assetPath: join(assets, entry.asset), outDir: join(folder, "out"), ...entry.options });
  return verdictAndValues(report, [folder, assets]);
}

export function differences(before: unknown, after: unknown, at = ""): string[] {
  if (JSON.stringify(before) === JSON.stringify(after)) return [];
  if (before !== null && after !== null && typeof before === "object" && typeof after === "object" && Array.isArray(before) === Array.isArray(after)) {
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    return [...keys].flatMap((key) => differences((before as Record<string, unknown>)[key], (after as Record<string, unknown>)[key], `${at}/${key}`));
  }
  return [`${at || "/"}: ${JSON.stringify(before)?.slice(0, 200)} became ${JSON.stringify(after)?.slice(0, 200)}`];
}
