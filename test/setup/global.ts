import type { TestProject } from "vitest/node";
import { BlenderNotFoundError } from "../../src/blender.js";
import { ensureFixtures } from "../../scripts/lib/fixtures.js";

declare module "vitest" {
  export interface ProvidedContext {
    fixtureSets: Record<string, { assets: string; markers: string }> | null;
  }
}

export const SKIP_VARIABLE = "BLENDWORKS_FIXTURES";

export default async function setup(project: TestProject): Promise<void> {
  if (process.env[SKIP_VARIABLE] === "skip") {
    project.provide("fixtureSets", null);
    return;
  }
  try {
    const sets = await ensureFixtures();
    project.provide("fixtureSets", Object.fromEntries(Object.entries(sets).map(([name, { assets, markers }]) => [name, { assets, markers }])));
  } catch (error) {
    if (!(error instanceof BlenderNotFoundError)) throw error;
    console.warn(`judge fixtures not generated: ${error.message.split("\n")[0]}`);
    project.provide("fixtureSets", null);
  }
}
