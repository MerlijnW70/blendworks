import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { repoRoot } from "./paths.js";

const BELONGS_ELSEWHERE = "an existing bound in a file that another job owns";

export const WALL_CLOCK_ALLOWED: Record<string, string> = {
  "test/mcp-routing-bench.test.ts": "the routing query bound belongs to another job",
  "test/mcp-connection.test.ts": BELONGS_ELSEWHERE,
  "test/mcp-long-calls.test.ts": BELONGS_ELSEWHERE,
  "test/judge/sandbox.test.ts": BELONGS_ELSEWHERE,
  "test/package/native-run.test.ts": BELONGS_ELSEWHERE,
};

const UPPER_BOUND = /\.(toBeLessThan|toBeLessThanOrEqual)\(/;
const TIME_WORDS = /performance\.now|Date\.now|hrtime|\bseconds\b|elapsed|\bduration\b|waited|\btook\b|\bms\b/i;
const TIME_NAMES = /[a-z]Ms\b|_MS\b/;

export type WallClockBound = { line: number; text: string };

export function wallClockBounds(source: string): WallClockBound[] {
  const found: WallClockBound[] = [];
  source.split("\n").forEach((text, index) => {
    if (UPPER_BOUND.test(text) && (TIME_WORDS.test(text) || TIME_NAMES.test(text))) found.push({ line: index + 1, text: text.trim() });
  });
  return found;
}

export function testSources(directory: string = join(repoRoot, "test"), prefix = "test/"): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return name === "node_modules" ? [] : testSources(path, `${prefix}${name}/`);
    return /\.ts$/.test(name) ? [`${prefix}${name}`] : [];
  });
}

export function offendingFiles(): Record<string, WallClockBound[]> {
  const out: Record<string, WallClockBound[]> = {};
  for (const file of testSources()) {
    if (file === "test/tooling/wall-clock-lint.test.ts") continue;
    const bounds = wallClockBounds(readFileSync(join(repoRoot, file), "utf8"));
    if (bounds.length > 0) out[file] = bounds;
  }
  return out;
}
