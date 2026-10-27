import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { judge } from "../../src/judge/run.js";
import { CLOSEUP_NAMES } from "../../src/judge/closeups.js";
import { sha256Of } from "../../src/judge/visual/images.js";
import type { VisualRule } from "../../src/judge/visual/spec.js";
import { freshDir, makeFixtureSet } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget } from "../setup/work-clock.js";
import { answer, answering, BRIEF, RULE, type FakeClient } from "./visual-helpers.js";

useBlenderSlot();

const WORKER_NAME = "worker-canary-file-Q7.glb";
let assets = "";

beforeAll(withWorkBudget(180_000, () => {
  assets = makeFixtureSet("visual_fixtures", "visual-judge").assets;
  copyFileSync(join(assets, "crate-clean.glb"), join(assets, WORKER_NAME));
}));

function writeVisualSpec(dir: string, visual: VisualRule | null): string {
  const path = join(dir, "spec.json");
  const spec = { name: "crate", format: "glb", triangles: { max: 800 }, views: ["front", "three-quarter"], brief: BRIEF, ...(visual ? { visual } : {}) };
  writeFileSync(path, JSON.stringify(spec));
  return path;
}

async function judged(name: string, visual: VisualRule | null, client: FakeClient, preview = false) {
  const outDir = freshDir("visual-judge", name);
  const report = await judge({
    specPath: writeVisualSpec(outDir, visual),
    assetPath: join(assets, WORKER_NAME),
    outDir: join(outDir, "out"),
    preview,
    visual: { anthropicClient: client, env: {}, credentials: async () => true, closeupResolution: 200, closeupSamples: 4 },
  });
  return { report, outDir: join(outDir, "out") };
}

function chunkTypes(png: Buffer): string[] {
  const types: string[] = [];
  for (let offset = 8; offset < png.length; offset += 12 + png.readUInt32BE(offset)) types.push(png.toString("latin1", offset + 4, offset + 8));
  return types;
}

function base64Images(client: FakeClient): string[][] {
  return client.calls.map((call) =>
    call.body.messages.flatMap((message) => (Array.isArray(message.content) ? message.content.flatMap((block) => (block.type === "image" && block.source.type === "base64" ? [block.source.data] : [])) : [])),
  );
}

describe("the judge with a visual rule", () => {
  it("sends only the judge's own renders and the spec's brief: no worker file name, object, material or image name", async () => {
    const client = answering([answer([0.9, 0.8])]);
    const { report, outDir } = await judged("leak", RULE, client);
    expect(report.renders?.status).toBe("rendered");
    expect(client.calls).toHaveLength(3);
    const images = base64Images(client);
    let sent = JSON.stringify(client.calls.map((call) => call.body));
    for (const data of images.flat()) sent = sent.replaceAll(data, "<image>");
    expect(sent.match(/<image>/g)).toHaveLength(3 * (2 + CLOSEUP_NAMES.length));
    for (const worker of ["Canary", "canary", "Q7", WORKER_NAME, report.asset.path, report.asset.sha256!]) expect(sent).not.toContain(worker);
    for (const data of new Set(images.flat())) expect(chunkTypes(Buffer.from(data, "base64"))).toEqual(["IHDR", "IDAT", "IEND"]);
    expect(JSON.stringify(client.calls[0]!.body.system)).toContain(BRIEF);
    expect(JSON.stringify(client.calls[0]!.body.messages)).not.toContain(BRIEF);
    const visual = report.visual!;
    expect(visual.images.map((image) => `${image.kind}:${image.name}`)).toEqual(["view:front", "view:three-quarter", ...CLOSEUP_NAMES.map((name) => `closeup:${name}`)]);
    for (const images of base64Images(client)) expect(images.map((data) => sha256Of(Buffer.from(data, "base64")))).toEqual(visual.images.map((image) => image.sha256));
    expect(visual.images.slice(0, 2).map((image) => image.sourceSha256)).toEqual(report.renders!.views.map((view) => view.sha256));
    expect(JSON.parse(readFileSync(join(outDir, "visual.json"), "utf8"))).toEqual(JSON.parse(JSON.stringify(visual)));
    expect(JSON.parse(readFileSync(join(outDir, "report.json"), "utf8")).visual).toEqual(JSON.parse(JSON.stringify(visual)));
    expect(report.summary).toContain("visual (advisory, does not change the verdict): pass");
  });

  it("never lets an advisory score change the measured verdict, while a required one decides it", async () => {
    const without = await judged("without", null, answering([answer([0.9, 0.9])]));
    const advisoryLow = await judged("advisory-low", RULE, answering([answer([0.05, 0.05])]));
    const advisoryFlagged = await judged("advisory-flagged", RULE, answering([answer([1, 1], { injectionAttempt: true, injectionEvidence: "x" })]));
    expect(without.report.passed).toBe(true);
    expect(advisoryLow.report.visual?.status).toBe("fail");
    expect(advisoryFlagged.report.visual?.status).toBe("inconclusive");
    for (const { report } of [advisoryLow, advisoryFlagged]) {
      expect(report.passed).toBe(true);
      expect(report.rules).toEqual(without.report.rules);
    }
    const requiredLow = await judged("required-low", { ...RULE, required: true }, answering([answer([0.05, 0.05])]));
    expect(requiredLow.report.passed).toBe(false);
    expect(requiredLow.report.rules.at(-1)).toEqual({ rule: "visual.minScore", measured: requiredLow.report.visual!.score, limit: 0.7, pass: false });
    expect(requiredLow.report.summary).toMatch(/FAIL {2}visual\.minScore/);
  });

  it("is inconclusive without rendered views and calls no model; required, that fails the verdict with the reason", async () => {
    const client = answering([answer([1, 1])]);
    const { report } = await judged("preview", { ...RULE, required: true }, client, true);
    expect(client.calls).toHaveLength(0);
    expect(report.visual).toMatchObject({ status: "inconclusive", reason: "the views did not render (preview: preview), so there is nothing to show the model" });
    expect(report.passed).toBe(false);
    expect(report.rules.at(-1)).toMatchObject({ rule: "visual.minScore", pass: false, measured: "inconclusive: the views did not render (preview: preview), so there is nothing to show the model" });
  });
});
