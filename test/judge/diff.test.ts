import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { main } from "../../src/judge/cli.js";
import { diffReports, diffText, readReport, type JudgeReport } from "../../src/judge/diff.js";
import { freshDir } from "./helpers.js";
import { CRATE_MEASUREMENTS } from "./measured.js";

const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);

function report(overrides: Partial<JudgeReport> = {}): JudgeReport {
  return {
    passed: true,
    spec: { path: "spec.json", sha256: "1".repeat(64) },
    asset: { path: "crate.glb", sha256: "2".repeat(64), setSha256: "3".repeat(64) },
    failure: null,
    rules: [
      { rule: "format", measured: "glb", limit: "glb", pass: true },
      { rule: "triangles.max", measured: 12, limit: 800, pass: true },
    ],
    measurements: { ...CRATE_MEASUREMENTS },
    renders: { views: [{ view: "front", path: "front.png", sha256: HASH_A }], contactSheet: "sheet.png", contactSheetSha256: HASH_A },
    ...overrides,
  };
}

describe("blendworks diff", () => {
  it("finds no difference between a report and itself", () => {
    expect(diffReports(report(), report())).toEqual([]);
    expect(diffText(report(), report(), [])).toContain("no differences");
  });

  it("names the changed verdict, rules, measurements and view hashes", () => {
    const revised = report({
      passed: false,
      rules: [
        { rule: "format", measured: "glb", limit: "glb", pass: true },
        { rule: "triangles.max", measured: 900, limit: 800, pass: false },
        { rule: "shells.max", measured: 3, limit: 1, pass: false },
      ],
      measurements: { ...CRATE_MEASUREMENTS, triangles: 900, size: [1, 1.2, 0.8] },
      renders: { views: [{ view: "front", path: "front.png", sha256: HASH_B }], contactSheet: "sheet.png", contactSheetSha256: HASH_A },
    });
    const changes = diffReports(report(), revised);
    expect(changes).toEqual([
      { kind: "verdict", path: "passed", before: true, after: false },
      { kind: "rule", path: "shells.max", before: null, after: { pass: false, measured: 3, limit: 1 } },
      { kind: "rule", path: "triangles.max", before: { pass: true, measured: 12, limit: 800 }, after: { pass: false, measured: 900, limit: 800 } },
      { kind: "measurement", path: "size", before: [1, 1, 0.8], after: [1, 1.2, 0.8] },
      { kind: "measurement", path: "triangles", before: 12, after: 900 },
      { kind: "image", path: "front", before: HASH_A, after: HASH_B },
    ]);
    const text = diffText(report(), revised, changes).split("\n");
    expect(text).toContain("rules: 2 changed");
    expect(text).toContain("  ~ triangles.max: pass -> FAIL; measured 12 -> 900");
    expect(text).toContain("  + shells.max: FAIL, measured 3, required 1");
    expect(text).toContain(`  ~ front: ${HASH_A} -> ${HASH_B}`);
  });

  it("exits 0 for matching reports, 1 for different ones and 2 for a file that is not a report", async () => {
    const dir = freshDir("diff");
    const first = join(dir, "a.json");
    const second = join(dir, "b.json");
    const broken = join(dir, "broken.json");
    writeFileSync(first, JSON.stringify(report()));
    writeFileSync(second, JSON.stringify(report({ passed: false })));
    writeFileSync(broken, JSON.stringify({ hello: "world" }));
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      expect(await main(["diff", first, first])).toBe(0);
      expect(await main(["diff", first, second])).toBe(1);
      expect(await main(["diff", first, second, "--json"])).toBe(1);
      expect(JSON.parse(String(log.mock.calls.at(-1)?.[0]))).toMatchObject({ same: false, changes: [{ kind: "verdict", path: "passed" }] });
      expect(await main(["diff", first, broken])).toBe(2);
      expect(await main(["diff", first])).toBe(2);
    } finally {
      log.mockRestore();
      error.mockRestore();
    }
    expect(readReport(first).passed).toBe(true);
  });
});
