import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { crc32 } from "node:zlib";
import { describe, expect, it } from "vitest";
import { parseSpec, SpecError } from "../../src/judge/spec.js";
import { IMAGE_CAP, prepareEvidence, sha256Of } from "../../src/judge/visual/images.js";
import { decodePng, downscale, encodePng, fitWithin, PngError } from "../../src/judge/visual/png.js";
import { combine, criterionScores, majority, median, overallScore, quorum, weightedMean } from "../../src/judge/visual/score.js";
import { resolveRule } from "../../src/judge/visual/spec.js";
import { freshDir } from "./helpers.js";
import { answer, BRIEF, RUBRIC, RULE, solidPng } from "./visual-helpers.js";

function specProblems(value: unknown): string[] {
  try {
    parseSpec(value);
  } catch (error) {
    if (error instanceof SpecError) return error.problems;
    throw error;
  }
  return [];
}

describe("the visual rule in the spec", () => {
  it("accepts the job's example and fills the documented defaults", () => {
    const spec = parseSpec({ format: "glb", brief: BRIEF, visual: RULE });
    expect(spec.visual).toEqual(RULE);
    expect(resolveRule({ rubric: RUBRIC }, {})).toEqual({ rubric: RUBRIC, minScore: 0.7, samples: 3, required: false, models: ["claude-opus-5-5"], modelSource: "default", committee: "min", effort: "high" });
  });

  it("takes the model from the spec, then the environment, then the default", () => {
    expect(resolveRule({ rubric: RUBRIC, model: "claude-sonnet-5-5" }, { BLENDWORKS_VISUAL_MODEL: "claude-haiku-5-5" }).models).toEqual(["claude-sonnet-5-5"]);
    expect(resolveRule({ rubric: RUBRIC }, { BLENDWORKS_VISUAL_MODEL: "claude-haiku-5-5" })).toMatchObject({ models: ["claude-haiku-5-5"], modelSource: "environment" });
  });

  it("refuses a visual rule without a brief, repeated ids, bad scores and mixed model fields", () => {
    expect(specProblems({ format: "glb", visual: RULE })).toEqual(["visual: the visual rule needs a brief"]);
    const found = specProblems({
      format: "glb",
      brief: BRIEF,
      visual: { rubric: [RUBRIC[0], RUBRIC[0]], minScore: 1.5, samples: 0, model: "claude-opus-5-5", models: ["a1", "b2"], committee: "min" },
    });
    expect(found).toContain("visual.rubric: rubric ids must not repeat");
    expect(found.some((problem) => problem.startsWith("visual.minScore:"))).toBe(true);
    expect(found.some((problem) => problem.startsWith("visual.samples:"))).toBe(true);
    expect(specProblems({ format: "glb", brief: BRIEF, visual: { rubric: RUBRIC, model: "claude-opus-5-5", models: ["claude-opus-5-5", "claude-sonnet-5-5"] } })).toEqual(["visual: use model or models, not both"]);
    expect(specProblems({ format: "glb", brief: BRIEF, visual: { rubric: RUBRIC, committee: "majority" } })).toEqual(["visual: committee needs models"]);
    expect(specProblems({ format: "glb", brief: BRIEF, visual: { rubric: [{ id: "Bad Id", question: "q", weight: 1 }] } }).some((problem) => problem.startsWith("visual.rubric.0.id:"))).toBe(true);
    expect(specProblems({ format: "glb", brief: BRIEF, visual: { rubric: [{ id: "a", question: "line one\nline two", weight: 1 }] } }).some((problem) => problem.startsWith("visual.rubric.0.question:"))).toBe(true);
  });
});

describe("the visual score", () => {
  it("takes the median of an odd and an even number of samples", () => {
    expect(median([0.9, 0.6, 0.8])).toBe(0.8);
    expect(median([1, 0.2, 0.9, 0.4])).toBeCloseTo(0.65, 12);
  });

  it("is the weighted mean of the per-criterion medians: (2 x 0.8 + 1 x 0.7) / 3", () => {
    const answers = [answer([0.9, 0.5]), answer([0.6, 1]), answer([0.8, 0.7])];
    const scores = criterionScores(RUBRIC, { "claude-opus-5-5": answers }, "min")!;
    expect(scores.map((entry) => entry.score)).toEqual([0.8, 0.7]);
    expect(overallScore(RUBRIC, scores)).toBeCloseTo(2.3 / 3, 12);
    expect(weightedMean(RUBRIC, { "matches-brief": 1, detail: 0 })).toBeCloseTo(2 / 3, 12);
  });

  it("combines a committee by the minimum or by the score a strict majority reaches", () => {
    expect(combine([0.9, 0.5, 0.7], "min")).toBe(0.5);
    expect(majority([0.9, 0.5, 0.7])).toBe(0.7);
    expect(majority([0.9, 0.5])).toBe(0.5);
    expect(majority([0.9, 0.8, 0.5, 0.3])).toBe(0.5);
    const scores = criterionScores(RUBRIC, { a: [answer([0.8, 0.7])], b: [answer([0.6, 0.9])] }, "min")!;
    expect(scores.map((entry) => entry.score)).toEqual([0.6, 0.7]);
    expect(overallScore(RUBRIC, scores)).toBeCloseTo(1.9 / 3, 12);
  });

  it("needs a strict majority of the samples to answer", () => {
    expect([1, 2, 3, 4, 9].map(quorum)).toEqual([1, 2, 2, 3, 5]);
    expect(criterionScores(RUBRIC, { a: [answer([1, 1])], b: [] }, "min")).toBeNull();
  });
});

function pngWithText(path: string, text: string): void {
  const plain = readFileSync(solidPng(path, 4, 4, [10, 20, 30]));
  const body = Buffer.from(`Scene\0${text}`, "latin1");
  const head = Buffer.alloc(8);
  head.writeUInt32BE(body.length, 0);
  head.write("tEXt", 4, "latin1");
  const tail = Buffer.alloc(4);
  tail.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), body])), 0);
  writeFileSync(path, Buffer.concat([plain.subarray(0, 33), head, body, tail, plain.subarray(33)]));
}

describe("the images sent to the model", () => {
  it("round-trips pixels through the PNG codec", () => {
    const rgba = Uint8Array.from({ length: 3 * 2 * 4 }, (_, index) => (index * 37) % 256);
    const decoded = decodePng(encodePng({ width: 3, height: 2, rgba }));
    expect(decoded).toEqual({ width: 3, height: 2, rgba });
  });

  it("fits the longer side within the cap and keeps the aspect", () => {
    expect(IMAGE_CAP).toBe(1024);
    expect(fitWithin(1200, 1200, 1024)).toEqual({ width: 1024, height: 1024 });
    expect(fitWithin(2000, 1000, 1024)).toEqual({ width: 1024, height: 512 });
    expect(fitWithin(512, 512, 1024)).toEqual({ width: 512, height: 512 });
  });

  it("averages in linear light: black and white make sRGB 188", () => {
    const rgba = new Uint8Array([0, 0, 0, 255, 255, 255, 255, 255]);
    expect(Array.from(downscale({ width: 2, height: 1, rgba }, 1, 1).rgba)).toEqual([188, 188, 188, 255]);
  });

  it("downscales over the cap, re-encodes every image and records both hashes", () => {
    const dir = freshDir("visual-images");
    const wide = solidPng(join(dir, "wide.png"), 2000, 1000, [90, 60, 30]);
    const small = join(dir, "small.png");
    pngWithText(small, "CANARY-TEXT-CHUNK");
    const evidence = prepareEvidence(
      [
        { name: "front", kind: "view", path: wide },
        { name: "hero", kind: "closeup", path: small },
      ],
      dir,
    );
    const [front, hero] = evidence.images;
    expect(front).toMatchObject({ width: 1024, height: 512, sourceWidth: 2000, sourceHeight: 1000, file: "visual/view-front.png", sourceSha256: sha256Of(readFileSync(wide)) });
    expect(hero).toMatchObject({ width: 4, height: 4, file: "visual/closeup-hero.png" });
    expect(front!.sha256).toBe(sha256Of(readFileSync(join(dir, front!.file))));
    expect(hero!.sha256).toBe(sha256Of(evidence.data[1]!));
    expect(readFileSync(small).toString("latin1")).toContain("CANARY-TEXT-CHUNK");
    expect(evidence.data[1]!.toString("latin1")).not.toContain("CANARY");
    expect(hero!.caption).toBe("Image 2 of 2: the hero close-up, rendered by the judge.");
  });

  it("refuses broken PNGs and names that are not the judge's", () => {
    const dir = freshDir("visual-broken");
    const path = solidPng(join(dir, "a.png"), 4, 4, [1, 2, 3]);
    const data = readFileSync(path);
    data[30] = data[30]! ^ 0xff;
    expect(() => decodePng(data)).toThrow(PngError);
    expect(() => decodePng(Buffer.from("not a png"))).toThrow("not a PNG file");
    expect(() => prepareEvidence([{ name: "../worker", kind: "view", path }], dir)).toThrow("is not a judge name");
    expect(() => prepareEvidence([], dir)).toThrow("no rendered images");
  });
});
