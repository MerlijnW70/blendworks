import { createHash } from "node:crypto";
import { mkdirSync, symlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { crc32 } from "node:zlib";
import { beforeAll, describe, expect, it } from "vitest";
import type { Measurements } from "../../src/judge/measurements.js";
import { loadReferences, referenceFrame, referenceRules, REFERENCE_LIMITS, type ReferenceRecord, type ReferenceView } from "../../src/judge/reference.js";
import { referenceRule, type ReferenceRule } from "../../src/judge/reference-spec.js";
import { maskFrom, maskImage } from "../../src/judge/silhouette.js";
import { fromBlender } from "../../src/judge/silhouettes.js";
import { StageFailure } from "../../src/judge/stages.js";
import { encodePng, PNG_SIGNATURE } from "../../src/judge/visual/png.js";
import { freshDir } from "./helpers.js";
import { CRATE_MEASUREMENTS } from "./measured.js";

let folder = "";
const SPEC = () => join(folder, "asset.spec.json");

function sha256(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

function chunk(type: string, body: Buffer): Buffer {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(body.length, 0);
  head.write(type, 4, "latin1");
  const tail = Buffer.alloc(4);
  tail.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), body])), 0);
  return Buffer.concat([head, body, tail]);
}

function header(width: number, height: number, interlace = 0): Buffer {
  const body = Buffer.alloc(13);
  body.writeUInt32BE(width, 0);
  body.writeUInt32BE(height, 4);
  body.set([8, 2, 0, 0, interlace], 8);
  return Buffer.concat([PNG_SIGNATURE, chunk("IHDR", body)]);
}

function squareMask(size: number): Buffer {
  return encodePng(maskImage(maskFrom(size, size, (x, y) => x >= size / 4 && x < (3 * size) / 4 && y >= size / 4 && y < (3 * size) / 4)));
}

function write(name: string, data: Buffer): string {
  writeFileSync(join(folder, name), data);
  return sha256(data);
}

function rule(mask: string, sha: string): ReferenceRule {
  return referenceRule.parse({ views: { front: { sha256: sha, mask } } });
}

function refused(mask: string, sha: string): { code: string; message: string } {
  try {
    loadReferences(rule(mask, sha), SPEC());
  } catch (error) {
    if (error instanceof StageFailure) return { code: error.failure.code, message: error.failure.message };
    throw error;
  }
  throw new Error("the reference was accepted");
}

beforeAll(() => {
  folder = freshDir("reference-inputs");
  writeFileSync(SPEC(), "{}");
});

describe("reference masks are untrusted input", () => {
  it("loads a pinned PNG mask beside the spec and reads it by luminance", () => {
    const sha = write("front.png", squareMask(64));
    const [loaded] = loadReferences(rule("front.png", sha), SPEC());
    expect(loaded).toMatchObject({ view: "front", mask: "front.png", sha256: sha, size: 64, channel: "luminance" });
    expect(loaded!.inside.inside.reduce((sum, value) => sum + value, 0)).toBe(32 * 32);
  });

  it("reads masks in a folder beside the spec", () => {
    mkdirSync(join(folder, "masks"), { recursive: true });
    const sha = write("masks/side.png", squareMask(32));
    expect(loadReferences(rule("masks/side.png", sha), SPEC())[0]?.size).toBe(32);
  });

  it("refuses a mask whose sha256 differs from the pinned one", () => {
    write("pinned.png", squareMask(64));
    expect(refused("pinned.png", "0".repeat(64))).toMatchObject({ code: "reference_sha256" });
  });

  it("refuses a missing mask, a folder and a link out of the spec's folder", () => {
    expect(refused("absent.png", "0".repeat(64)).code).toBe("reference_missing");
    mkdirSync(join(folder, "folder.png"), { recursive: true });
    expect(refused("folder.png", "0".repeat(64)).code).toBe("reference_not_a_file");
    const outside = freshDir("reference-outside");
    const data = squareMask(64);
    writeFileSync(join(outside, "secret.png"), data);
    try {
      symlinkSync(join(outside, "secret.png"), join(folder, "link.png"));
    } catch {
      return;
    }
    expect(refused("link.png", sha256(data)).code).toBe("reference_outside");
  });

  it("refuses a file over the size limit before reading it as an image", () => {
    const sha = write("huge.png", Buffer.concat([squareMask(64), Buffer.alloc(REFERENCE_LIMITS.maxBytes)]));
    expect(refused("huge.png", sha)).toMatchObject({ code: "reference_too_large" });
  });

  it("refuses an image that is not square, too small or too large, from its header alone", () => {
    const wide = encodePng(maskImage(maskFrom(64, 32, () => true)));
    expect(refused("wide.png", write("wide.png", wide))).toMatchObject({ code: "reference_dimensions", message: "the front reference is 64 x 32 pixels; it must be square" });
    const tiny = squareMask(8);
    expect(refused("tiny.png", write("tiny.png", tiny)).code).toBe("reference_dimensions");
    const bomb = Buffer.concat([header(65536, 65536), chunk("IEND", Buffer.alloc(0))]);
    expect(refused("bomb.png", write("bomb.png", bomb))).toMatchObject({ code: "reference_dimensions", message: "the front reference is 65536 pixels on a side; it must be 16 to 2048" });
  });

  it("refuses what is not a well-formed PNG", () => {
    expect(refused("text.png", write("text.png", Buffer.from("not an image at all, just text that is long enough"))).code).toBe("reference_format");
    const good = squareMask(64);
    const flipped = Buffer.from(good);
    flipped[flipped.length - 20] = flipped[flipped.length - 20]! ^ 0xff;
    expect(refused("crc.png", write("crc.png", flipped))).toMatchObject({ code: "reference_format" });
    expect(refused("cut.png", write("cut.png", good.subarray(0, good.length - 30))).code).toBe("reference_format");
    const interlaced = Buffer.concat([header(64, 64, 1), chunk("IEND", Buffer.alloc(0))]);
    expect(refused("interlaced.png", write("interlaced.png", interlaced))).toMatchObject({ code: "reference_format" });
  });
});

function view(name: string, iou: number, boundaryDistance: number | null): ReferenceView {
  const base = { mask: `${name}.png`, sha256: "0".repeat(64), bytes: 1, size: 64, channel: "luminance" as const, assetPixels: 0, referencePixels: 0, intersection: 0, union: 0 };
  return { ...base, view: name, iou, boundaryDistance, boundaryPixels: boundaryDistance, edges: { asset: 1, reference: 1 }, silhouette: "", silhouetteSha256: "", overlay: "", overlaySha256: "" };
}

describe("the reference rules", () => {
  const sha256 = "0".repeat(64);
  const record: ReferenceRecord = { frame: { source: "asset", min: [0, 0, 0], max: [1, 1, 1] }, views: [view("front", 0.95, 0.01), view("left", 0.8, 0.03)] };

  it("judge the worst view against the overall limit", () => {
    const spec = referenceRule.parse({ views: { front: { sha256, mask: "front.png" }, left: { sha256, mask: "left.png" } }, minIoU: 0.9, maxBoundaryDistance: 0.02 });
    expect(referenceRules(spec, record)).toEqual([
      { rule: "reference.minIoU", measured: { worst: 0.8, views: { front: 0.95, left: 0.8 } }, limit: 0.9, pass: false },
      { rule: "reference.maxBoundaryDistance", measured: { worst: 0.03, views: { front: 0.01, left: 0.03 } }, limit: 0.02, pass: false },
    ]);
  });

  it("judge a view with its own limit on its own, and the others against the overall limit", () => {
    const spec = referenceRule.parse({ views: { front: { sha256, mask: "front.png" }, left: { sha256, mask: "left.png", minIoU: 0.75 } }, minIoU: 0.9 });
    expect(referenceRules(spec, record)).toEqual([
      { rule: "reference.minIoU", measured: { worst: 0.95, views: { front: 0.95 } }, limit: 0.9, pass: true },
      { rule: "reference[left].minIoU", measured: 0.8, limit: 0.75, pass: true },
    ]);
  });

  it("fail a boundary limit when one silhouette is empty", () => {
    const spec = referenceRule.parse({ views: { front: { sha256, mask: "front.png", maxBoundaryDistance: 0.5 } } });
    expect(referenceRules(spec, { ...record, views: [view("front", 0, null)] })).toEqual([{ rule: "reference[front].maxBoundaryDistance", measured: null, limit: 0.5, pass: false }]);
  });

  it("frame on the asset's bounds and origin, or on the spec's bounds in its own axes", () => {
    const measured: Measurements = { ...CRATE_MEASUREMENTS };
    const spec = referenceRule.parse({ views: { front: { sha256, mask: "front.png" } } });
    expect(referenceFrame(spec, measured, "z")).toEqual({ source: "asset", min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8], origin: [0, 0, 0] });
    const boxed = referenceRule.parse({ ...spec, bounds: { min: [-1, 0, -2], max: [1, 3, 2] } });
    expect(referenceFrame(boxed, measured, "z")).toEqual({ source: "spec", min: [-1, 0, -2], max: [1, 3, 2], origin: [0, 1.5, 0] });
    expect(referenceFrame(boxed, measured, "y")).toEqual({ source: "spec", min: [-1, -2, 0], max: [1, 2, 3], origin: [0, 0, 1.5] });
    expect(fromBlender([1, -2, 3], "y")).toEqual([1, 3, 2]);
  });
});
