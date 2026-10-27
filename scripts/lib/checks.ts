import { changedFiles, discoverTests, selectRelated } from "./fast-map.js";
import { npmStep, runPhases, type Step } from "./pipeline.js";

export function fullPhases(): Step[][] {
  return [
    [npmStep("rules"), npmStep("typecheck"), npmStep("build")],
    [npmStep("test"), npmStep("test:bridge"), npmStep("build:addon")],
  ];
}

export function fastPhases(vitest: string[], bridge: string[], needsFixtures: boolean): Step[][] {
  const second: Step[] = [npmStep("test", vitest, needsFixtures ? undefined : { BLENDWORKS_FIXTURES: "skip" })];
  if (bridge.length > 0) second.push(npmStep("test:bridge", bridge));
  return [[npmStep("rules"), npmStep("typecheck")], second];
}

export async function checkMain(): Promise<number> {
  const { passed } = await runPhases(fullPhases());
  return passed ? 0 : 1;
}

export async function fastMain(): Promise<number> {
  const tests = discoverTests();
  const changed = changedFiles();
  const selection = selectRelated(changed, tests);
  console.log(`changed files: ${changed.length === 0 ? "none" : changed.length}`);
  for (const reason of selection.reasons) console.log(`  ${reason}`);
  const needsFixtures = selection.vitest.some((file) => tests.blender.includes(file));
  const blender = selection.vitest.filter((file) => tests.blender.includes(file));
  console.log(`unit tests: ${selection.vitest.length - blender.length}; Blender tests: ${blender.length}; bridge test files: ${selection.bridge.length}`);
  const { passed } = await runPhases(fastPhases(selection.vitest, selection.bridge, needsFixtures));
  return passed ? 0 : 1;
}
