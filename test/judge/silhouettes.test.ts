import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Report } from "../../src/judge/report.js";
import { judge } from "../../src/judge/run.js";
import { maskFrom, maskImage } from "../../src/judge/silhouette.js";
import { silhouettes } from "../../src/judge/silhouettes.js";
import { encodePng } from "../../src/judge/visual/png.js";
import { freshDir, makeFixtures } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

let assets = "";
let folder = "";

beforeAll(withWorkBudget(180_000, () => {
  ({ assets } = makeFixtures("silhouettes"));
  folder = freshDir("silhouettes", "specs");
}));

const SIZE = 512;
const ACROSS = 1.18;
const PIXELS_PER_METRE = SIZE / ACROSS;

function covered(halfWidth: number): [number, number] {
  const reach = halfWidth * PIXELS_PER_METRE;
  return [Math.ceil(SIZE / 2 - 0.5 - reach), Math.floor(SIZE / 2 - 0.5 + reach)];
}

const [LEFT, RIGHT] = covered(0.5);
const [TOP, BOTTOM] = covered(0.4);

function rectangle(shift = 0): Buffer {
  return encodePng(maskImage(maskFrom(SIZE, SIZE, (x, y) => x >= LEFT + shift && x <= RIGHT + shift && y >= TOP && y <= BOTTOM)));
}

function sha256(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

async function compared(asset: string, name: string, reference: Record<string, unknown>): Promise<Report> {
  const spec = join(folder, `${name}.spec.json`);
  writeFileSync(spec, JSON.stringify({ format: "glb", views: ["front"], reference }));
  return judge({ specPath: spec, assetPath: join(assets, asset), outDir: freshDir("silhouettes", "reports", name), preview: true });
}

function front(data: Buffer, name: string, limits: Record<string, unknown> = {}): Record<string, unknown> {
  writeFileSync(join(folder, name), data);
  return { views: { front: { sha256: sha256(data), mask: name } }, ...limits };
}

describe("the reference comparison", workBudget(180_000), () => {
  it("frames the crate as the judge's front view does: 434 x 348 pixels, IoU 1 against that rectangle", async () => {
    expect([LEFT, RIGHT, TOP, BOTTOM]).toEqual([39, 472, 82, 429]);
    const report = await compared("crate.glb", "exact", front(rectangle(), "exact.png", { minIoU: 1, maxBoundaryDistance: 0 }));
    expect(report.failure).toBeNull();
    expect(report.passed).toBe(true);
    const [view] = report.reference!.views;
    expect(view).toMatchObject({ view: "front", size: 512, channel: "luminance", assetPixels: 434 * 348, referencePixels: 434 * 348, iou: 1, boundaryDistance: 0 });
    expect(report.reference!.frame).toEqual({ source: "asset", min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] });
    expect(sha256(readFileSync(view!.silhouette))).toBe(view!.silhouetteSha256);
    expect(existsSync(view!.overlay)).toBe(true);
  });

  it("scores the rectangle moved 20 pixels right at IoU 414/454 and a mean edge distance of 27760/3120 pixels", async () => {
    const report = await compared("crate.glb", "shifted", front(rectangle(20), "shifted.png", { minIoU: 0.95, maxBoundaryDistance: 0.02 }));
    expect(report.rules.map((rule) => [rule.rule, rule.pass])).toEqual([
      ["format", true],
      ["reference.minIoU", false],
      ["reference.maxBoundaryDistance", true],
    ]);
    expect(report.reference!.views[0]).toMatchObject({ intersection: 414 * 348, union: 454 * 348, iou: Math.round((414 / 454) * 1e6) / 1e6, edges: { asset: 1560, reference: 1560 } });
    const sides = 348 * 20;
    const corners = 2 * 190 + 308 * 20;
    const ends = 2 * 190;
    expect(report.reference!.views[0]!.boundaryPixels).toBeCloseTo((2 * (sides + corners + ends)) / 3120, 5);
    expect(report.reference!.views[0]!.boundaryDistance).toBeCloseTo((2 * (sides + corners + ends)) / 3120 / 512, 5);
  });

  it("makes masks with the silhouettes command that score the asset IoU 1 and a wider crate 434/512", async () => {
    const made = await silhouettes({ assetPath: join(assets, "crate.glb"), outDir: freshDir("silhouettes", "masks"), views: ["front", "three-quarter"], size: SIZE });
    expect(made.masks.map((mask) => [mask.view, mask.pixels])).toEqual([
      ["front", 434 * 348],
      ["three-quarter", made.masks[1]!.pixels],
    ]);
    expect(made.reference.bounds).toEqual({ min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] });
    for (const mask of made.masks) writeFileSync(join(folder, `made-${mask.view}.png`), readFileSync(mask.path));
    const views = Object.fromEntries(made.masks.map((mask) => [mask.view, { sha256: mask.sha256, mask: `made-${mask.view}.png` }]));
    const reference = { views, bounds: made.reference.bounds, minIoU: 0.99 };
    const same = await compared("crate.glb", "made", reference);
    expect(same.passed).toBe(true);
    expect(same.reference!.views.map((view) => [view.view, view.iou, view.boundaryDistance])).toEqual([
      ["front", 1, 0],
      ["three-quarter", 1, 0],
    ]);
    expect(same.reference!.frame.source).toBe("spec");
    const wide = await compared("wrong-size.glb", "made-wide", reference);
    expect(wide.passed).toBe(false);
    expect(wide.reference!.views[0]).toMatchObject({ assetPixels: 512 * 348, intersection: 434 * 348, iou: Math.round((434 / 512) * 1e6) / 1e6 });
  });

  it("refuses a mask that does not match its pinned sha256 before Blender starts", async () => {
    writeFileSync(join(folder, "swapped.png"), rectangle(5));
    const report = await compared("crate.glb", "swapped", { views: { front: { sha256: sha256(rectangle()), mask: "swapped.png" } }, minIoU: 0.5 });
    expect(report.passed).toBe(false);
    expect(report.failure).toMatchObject({ stage: "reference", code: "reference_sha256" });
    expect(report.measurements).toBeNull();
    expect(report.rules[0]).toMatchObject({ rule: "reference", pass: false });
  });
});
