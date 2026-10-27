import { relative, sep } from "node:path";
import { BaseSequencer, type TestSpecification } from "vitest/node";
import { knownDurations, type Durations } from "../../scripts/lib/durations.js";
import { repoRoot } from "../../scripts/lib/paths.js";

export function testKey(moduleId: string): string {
  return relative(repoRoot, moduleId).split(sep).join("/");
}

export function heaviestFirst(keys: string[], durations: Durations): string[] {
  const position = new Map(keys.map((key, index) => [key, index]));
  const expected = (key: string) => durations[key] ?? Number.POSITIVE_INFINITY;
  return [...keys].sort((a, b) => expected(b) - expected(a) || (position.get(a) ?? 0) - (position.get(b) ?? 0));
}

export default class HeaviestFirstSequencer extends BaseSequencer {
  override async sort(files: TestSpecification[]): Promise<TestSpecification[]> {
    const base = await super.sort(files);
    const byKey = new Map(base.map((spec) => [testKey(spec.moduleId), spec]));
    return heaviestFirst([...byKey.keys()], knownDurations()).map((key) => byKey.get(key) as TestSpecification);
  }
}
