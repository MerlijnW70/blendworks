import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { checkReference, REFUSAL_REASONS, type ReferenceStyle } from "../../src/judge/path-policy.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { workBudget } from "../setup/work-clock.js";

useBlenderSlot();

type Case = { raw: string; style: ReferenceStyle; path?: string; refused?: string; repeat?: number };
type Outcome = { path: string } | { refused: string; reason: string };

const PROBE = fileURLToPath(new URL("./path_policy_probe.py", import.meta.url));
const TOKENS = /LONG_SEGMENT|LONG_PATH|LONG_OK/;

function expand(entry: Case): Case {
  if (entry.repeat === undefined) return entry;
  const filler = "a".repeat(entry.repeat);
  return { ...entry, raw: entry.raw.replace(TOKENS, filler), ...(entry.path === undefined ? {} : { path: entry.path.replace(TOKENS, filler) }) };
}

const CASES = (JSON.parse(readFileSync(fileURLToPath(new URL("./path-policy-cases.json", import.meta.url)), "utf8")) as Case[]).map(expand);

function expected(entry: Case): Outcome {
  if (entry.path !== undefined) return { path: entry.path };
  return { refused: entry.refused!, reason: REFUSAL_REASONS[entry.refused as keyof typeof REFUSAL_REASONS] };
}

function typescriptOutcome(entry: Case): Outcome {
  const verdict = checkReference(entry.raw, entry.style);
  return verdict.ok ? { path: verdict.path } : { refused: verdict.code, reason: verdict.reason };
}

describe("one path policy for every reference the judge may open", () => {
  it("covers every refusal kind in its table", () => {
    const kinds = new Set(CASES.flatMap((entry) => (entry.refused === undefined ? [] : [entry.refused])));
    expect([...kinds].sort()).toEqual(Object.keys(REFUSAL_REASONS).sort());
    expect(new Set(CASES.map((entry) => entry.style))).toEqual(new Set(["path", "uri", "blend"]));
  });

  it.each(CASES.map((entry) => [JSON.stringify(entry.raw).slice(0, 60), entry.style, entry] as const))("in TypeScript: %s as %s", (_, __, entry) => {
    expect(typescriptOutcome(entry)).toEqual(expected(entry));
  });

  it("in Blender's Python gives the same answer for every entry of the table", workBudget(60_000), () => {
    const folder = freshDir("path-policy");
    const casesPath = join(folder, "cases.json");
    const outPath = join(folder, "results.json");
    writeFileSync(casesPath, JSON.stringify(CASES));
    execFileSync(blenderPath(), ["--background", "--factory-startup", "--python-exit-code", "1", "--python", PROBE, "--", SCRIPTS_DIR, casesPath, outPath], { stdio: "ignore", timeout: 55_000 });
    const results = JSON.parse(readFileSync(outPath, "utf8")) as Outcome[];
    expect(results).toHaveLength(CASES.length);
    CASES.forEach((entry, index) => expect(results[index], JSON.stringify(entry.raw).slice(0, 80)).toEqual(expected(entry)));
  });
});
