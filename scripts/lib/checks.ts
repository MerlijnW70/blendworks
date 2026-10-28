import { join } from "node:path";
import { blenderJobs } from "../../src/blender.js";
import { execFileSync } from "node:child_process";
import { describeChange, rememberDurations, saveBaseline } from "./durations.js";
import { changedFiles, discoverTests, selectRelated } from "./fast-map.js";
import { cacheRoot, repoRoot } from "./paths.js";
import { npmStep, runPhases, type Step } from "./pipeline.js";
import { readTimingLog, timingReport, TIMINGS_VARIABLE } from "./timings.js";

export function fullPhases(): Step[][] {
  return [[npmStep("rules"), npmStep("typecheck"), npmStep("build"), npmStep("build:addon"), npmStep("test"), npmStep("test:bridge")]];
}

export function fastPhases(vitest: string[], bridge: string[], needsFixtures: boolean): Step[][] {
  const phase: Step[] = [npmStep("rules"), npmStep("typecheck"), npmStep("test", vitest, needsFixtures ? {} : { BLENDWORKS_FIXTURES: "skip" })];
  if (bridge.length > 0) phase.push(npmStep("test:bridge", bridge));
  return [phase];
}

export function timingLogPath(name: string, env: NodeJS.ProcessEnv = process.env): string {
  return join(cacheRoot(env), "timings", `${name}-${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`);
}

function git(args: string[]): string {
  try {
    return execFileSync("git", args, { cwd: repoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "?";
  }
}

export function onCleanMain(): boolean {
  return git(["rev-parse", "--abbrev-ref", "HEAD"]) === "main" && git(["status", "--porcelain"]) === "";
}

async function timedPhases(name: string, phases: Step[][], refreshBaseline = false): Promise<boolean> {
  const log = timingLogPath(name);
  process.env[TIMINGS_VARIABLE] = log;
  const { passed, seconds } = await runPhases(phases);
  const timings = readTimingLog(log);
  for (const line of timingReport(timings, seconds, blenderJobs())) console.log(line);
  rememberDurations(timings);
  if (passed && refreshBaseline) for (const line of describeChange(saveBaseline())) console.log(line);
  return passed;
}

export async function checkMain(): Promise<number> {
  return (await timedPhases("check", fullPhases(), onCleanMain())) ? 0 : 1;
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
  return (await timedPhases("check-fast", fastPhases(selection.vitest, selection.bridge, needsFixtures))) ? 0 : 1;
}
