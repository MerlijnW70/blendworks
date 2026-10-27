import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const BLENDER_TOKENS = [/blenderPath\(/, /makeFixtures\(/, /startHeadlessSession\(/, /startSession\(/, /[^.\w]judge\(/, /[^.\w]closeups\(/, /session\.py/];
const SLOT_CALL = "useBlenderSlot(";

function testFiles(directory: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(directory)) {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) out.push(...testFiles(path));
    else if (name.endsWith(".test.ts")) out.push(path);
  }
  return out;
}

describe("test files that start Blender", () => {
  const files = testFiles("test").filter((file) => !relative("test", file).startsWith(`tooling${sep}`));

  it("each take a Blender slot, so the process cap holds for every file", () => {
    const missing = files
      .filter((file) => BLENDER_TOKENS.some((token) => token.test(readFileSync(file, "utf8"))))
      .filter((file) => !readFileSync(file, "utf8").includes(SLOT_CALL))
      .map((file) => relative(".", file).split(sep).join("/"));
    expect(missing).toEqual([]);
  });

  it("never take a slot without starting Blender", () => {
    const idle = files
      .filter((file) => readFileSync(file, "utf8").includes(SLOT_CALL))
      .filter((file) => !BLENDER_TOKENS.some((token) => token.test(readFileSync(file, "utf8"))))
      .map((file) => relative(".", file).split(sep).join("/"));
    expect(idle).toEqual([]);
  });
});
