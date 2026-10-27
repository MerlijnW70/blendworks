import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseCommand, UsageError } from "../../src/judge/cli.js";
import type { Report } from "../../src/judge/report.js";
import type { JudgeOptions } from "../../src/judge/run.js";
import { readSpec } from "../../src/judge/spec.js";
import { EvalError, evalText, readLabelled, resolveEntryPath, visualEval } from "../../src/judge/visual/eval.js";
import { baseRecord } from "../../src/judge/visual/stage.js";
import type { VisualStatus } from "../../src/judge/visual/record.js";
import { freshDir } from "./helpers.js";
import { RULE } from "./visual-helpers.js";

const SHIPPED = "test/fixtures/visual/labelled.json";

function fakeReport(status: VisualStatus, score: number | null, costUsd: number | null): Report {
  const visual = { ...baseRecord(RULE, {}), status, score, costUsd, reason: status === "inconclusive" ? "no credentials" : null };
  visual.usage = { inputTokens: 100, outputTokens: 10, cacheCreationInputTokens: 0, cacheReadInputTokens: 50 };
  return { passed: true, failure: null, visual } as unknown as Report;
}

describe("visual-eval", () => {
  it("ships a labelled set of proof passes and wrong-brief, blockout, injected and gaming fails", () => {
    const labelled = readLabelled(SHIPPED);
    const expected = Object.fromEntries(labelled.entries.map((entry) => [entry.id, entry.expected]));
    expect(Object.entries(expected).filter(([, value]) => value === "pass").map(([id]) => id)).toEqual(["crate-proof", "torch-proof", "rocks-proof", "pickaxe-proof", "drill-rig-proof", "armillary-proof"]);
    expect(expected).toMatchObject({ "torch-as-crate": "fail", "blockout-as-crate": "fail", "injected-crate": "fail", "gaming-padded": "fail", "gaming-inverted": "fail" });
    const scripts = { visual: readFileSync("test/judge/visual_fixtures.py", "utf8"), integrity: readFileSync("test/judge/integrity_fixtures.py", "utf8") };
    for (const entry of labelled.entries) {
      const spec = readSpec(resolve("test/fixtures/visual", entry.spec));
      expect(spec.visual?.required).toBe(true);
      const [, root, file] = /^\$(\w+)\/(.+)$/.exec(entry.asset)!;
      expect(["proof", "visual", "integrity"]).toContain(root);
      if (root !== "proof") expect(scripts[root as "visual" | "integrity"]).toContain(`"${file}"`);
    }
  });

  it("resolves $name/ paths through --dir and other paths from the labelled file", () => {
    expect(resolveEntryPath("$proof/torch.glb", "/base", { proof: "/assets" })).toBe(resolve("/assets", "torch.glb"));
    expect(resolveEntryPath("specs/crate.json", "/base", {})).toBe(resolve("/base", "specs/crate.json"));
    expect(() => resolveEntryPath("$visual/blockout.glb", "/base", {})).toThrow(new EvalError("$visual/blockout.glb needs --dir visual=<folder>"));
  });

  it("reports agreement, false passes, false fails, inconclusive entries, tokens and cost", async () => {
    const dir = freshDir("visual-eval");
    const labelledPath = join(dir, "labelled.json");
    writeFileSync(
      labelledPath,
      JSON.stringify({
        entries: [
          { id: "good", asset: "$a/good.glb", spec: "s.json", expected: "pass" },
          { id: "missed", asset: "$a/missed.glb", spec: "s.json", expected: "pass" },
          { id: "fooled", asset: "$a/fooled.glb", spec: "s.json", expected: "fail" },
          { id: "caught", asset: "$a/caught.glb", spec: "s.json", expected: "fail" },
        ],
      }),
    );
    const results: Record<string, Report> = {
      "good.glb": fakeReport("pass", 0.9, 0.1),
      "missed.glb": fakeReport("inconclusive", null, 0),
      "fooled.glb": fakeReport("pass", 0.8, 0.2),
      "caught.glb": fakeReport("fail", 0.3, 0.05),
    };
    const seen: JudgeOptions[] = [];
    const report = await visualEval({
      labelledPath,
      outDir: join(dir, "out"),
      dirs: { a: join(dir, "assets") },
      judge: async (options) => {
        seen.push(options);
        return results[options.assetPath.split(/[\\/]/).at(-1)!]!;
      },
      judgeOptions: { device: "cpu" },
    });
    expect(seen.map((options) => [options.specPath, options.outDir, options.device])).toEqual(["good", "missed", "fooled", "caught"].map((id) => [join(dir, "s.json"), join(dir, "out", id), "cpu"]));
    expect(report).toMatchObject({ total: 4, agreed: 2, agreement: 0.5, falsePasses: ["fooled"], falseFails: ["missed"], inconclusive: ["missed"] });
    expect(report.costUsd).toBeCloseTo(0.35, 12);
    expect(report.usage).toEqual({ inputTokens: 400, outputTokens: 40, cacheCreationInputTokens: 0, cacheReadInputTokens: 200 });
    expect(JSON.parse(readFileSync(join(dir, "out", "visual-eval.json"), "utf8"))).toEqual(JSON.parse(JSON.stringify(report)));
    const text = evalText(report);
    expect(text.split("\n").slice(0, 4)).toEqual(["visual-eval: 2 of 4 agree (50.0 %)", "  false passes: fooled", "  false fails: missed", "  inconclusive: missed"]);
    expect(text).toContain("missed: expected pass, got inconclusive (no credentials)");
  });

  it("parses the command with repeated --dir options", () => {
    expect(parseCommand(["visual-eval", SHIPPED, "--dir", "proof=artifacts/proof", "--dir", "visual=x", "--out", "o"])).toMatchObject({
      command: "visual-eval",
      labelledPath: SHIPPED,
      outDir: "o",
      dirs: { proof: "artifacts/proof", visual: "x" },
    });
    expect(() => parseCommand(["visual-eval", SHIPPED, "--dir", "proof"])).toThrow(UsageError);
    expect(() => parseCommand(["visual-eval"])).toThrow(UsageError);
  });
});
