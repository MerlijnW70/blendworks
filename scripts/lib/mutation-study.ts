import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, posix } from "node:path";
import { FIXTURE_BUILD, isTestFile, type Repo, selectAffected, sharedReason } from "./affected.js";
import { buildGraph, repoSource } from "./dep-graph.js";
import { mutate, type Mutant } from "./mutation.js";
import { cacheRoot, repoRoot } from "./paths.js";
import { npmStep, runPhases } from "./pipeline.js";
import type { FileEvent } from "./progress.js";
import { TIMINGS_VARIABLE } from "./timings.js";
import { timingLogPath } from "./checks.js";

export type SuiteResult = { failing: string[]; files: number; fixtureBuildFailed: boolean; seconds: number };

export type Suite = (root: string, only?: string[]) => Promise<SuiteResult>;

export type ModuleResult = { module: string; functions: number; failing: string[]; selected: number; everything: boolean; missed: string[]; seconds: number };

export type Study = { baseline: string[]; results: ModuleResult[]; skipped: string[] };

export const STRATA: [string, RegExp][] = [
  ["MCP server", /^src\/mcp\/.*\.ts$/],
  ["judge", /^src\/judge\/.*\.ts$/],
  ["packaging", /^src\/package\/.*\.ts$/],
  ["bridge commands", /^bridge\/blendworks_bridge\/commands\/\w+\.py$/],
  ["bridge modules", /^bridge\/blendworks_bridge\/\w+\.py$/],
  ["judge scripts", /^bridge\/judge\/\w+\.py$/],
  ["package scripts", /^bridge\/package\/\w+\.py$/],
];

export function chooseModules(files: string[], count: number, read: (file: string) => string | undefined): string[] {
  const strata = STRATA.map(([, pattern]) => files.filter((file) => pattern.test(file) && sharedReason(file) === undefined && !isTestFile(file) && mutate(file, read(file) ?? "").functions > 0).sort());
  const total = strata.reduce((sum, list) => sum + list.length, 0);
  const shares = strata.map((list) => (list.length === 0 ? 0 : Math.max(2, Math.round((count * list.length) / total))));
  const adjust = (step: number): void => {
    const largest = shares.indexOf(Math.max(...shares));
    shares[largest] = (shares[largest] ?? 0) + step;
  };
  while (shares.reduce((a, b) => a + b, 0) > count) adjust(-1);
  while (shares.reduce((a, b) => a + b, 0) < count) adjust(1);
  return strata.flatMap((list, index) => {
    const take = Math.min(list.length, shares[index] ?? 0);
    return Array.from({ length: take }, (_, at) => list[Math.floor(((at + 0.5) * list.length) / take)] as string);
  });
}

const RECOVERY = "mutation-recovery.json";

export function restorePending(root: string, cache: string = cacheRoot()): string[] {
  const marker = join(cache, RECOVERY);
  if (!existsSync(marker)) return [];
  const saved = JSON.parse(readFileSync(marker, "utf8")) as { file: string; text: string }[];
  for (const { file, text } of saved) writeFileSync(join(root, file), text);
  rmSync(marker);
  return saved.map(({ file }) => file);
}

export async function withMutants<T>(root: string, mutants: Mutant[], run: () => Promise<T>, cache: string = cacheRoot()): Promise<T> {
  const originals = mutants.map((mutant) => ({ file: mutant.file, text: readFileSync(join(root, mutant.file), "utf8") }));
  mkdirSync(cache, { recursive: true });
  writeFileSync(join(cache, RECOVERY), JSON.stringify(originals));
  for (const mutant of mutants) writeFileSync(join(root, mutant.file), mutant.text);
  try {
    return await run();
  } finally {
    for (const { file, text } of originals) writeFileSync(join(root, file), text);
    rmSync(join(cache, RECOVERY), { force: true });
  }
}

export function selectionFor(root: string, file: string, original: string, lines: number[]): { selected: Set<string>; everything: boolean } {
  const source = repoSource(root);
  const repo: Repo = { source, graph: buildGraph(source), base: (name) => (name === file ? original : source.read(name)) };
  const selection = selectAffected([{ file, status: "M", baseLines: [], headLines: lines }], repo);
  const selected = new Set([...selection.vitest, ...selection.bridge]);
  if (selection.fixtures) selected.add(FIXTURE_BUILD);
  return { selected, everything: selection.everything };
}

function failures(run: SuiteResult, baseline: string[]): string[] {
  return [...(run.fixtureBuildFailed ? [FIXTURE_BUILD] : []), ...run.failing].filter((file) => !baseline.includes(file));
}

export type Selector = (root: string, file: string, original: string, lines: number[]) => { selected: Set<string>; everything: boolean };

export type StudyOptions = { group?: number; log?: (line: string) => void; cache?: string; select?: Selector };

export async function runStudy(root: string, modules: string[], suite: Suite, options: StudyOptions = {}): Promise<Study> {
  const log = options.log ?? ((line: string) => console.log(line));
  const group = Math.max(1, options.group ?? 1);
  const cache = options.cache ?? cacheRoot();
  const select = options.select ?? selectionFor;
  const recovered = restorePending(root, cache);
  if (recovered.length > 0) log(`restored ${recovered.join(", ")} from an earlier run that stopped while they were mutated`);
  const base = await suite(root);
  const baseline = failures(base, []);
  log(`baseline: ${base.files} test files, ${baseline.length} failing without a mutant${baseline.length > 0 ? `: ${baseline.join(", ")}` : ""} (${base.seconds.toFixed(0)} s)`);
  const results: ModuleResult[] = [];
  const skipped: string[] = [];
  const mutants: { mutant: Mutant; original: string }[] = [];
  for (const module of modules) {
    const original = readFileSync(join(root, module), "utf8");
    const mutant = mutate(module, original);
    if (mutant.functions === 0) {
      skipped.push(module);
      log(`skip ${module}: no function to break`);
    } else mutants.push({ mutant, original });
  }
  for (let at = 0; at < mutants.length; at += group) {
    const batch = mutants.slice(at, at + group);
    const outcome = await withMutants(root, batch.map((entry) => entry.mutant), async () => ({ run: await suite(root), selections: batch.map((entry) => select(root, entry.mutant.file, entry.original, entry.mutant.lines)) }), cache);
    const failing = failures(outcome.run, baseline);
    if (batch.length > 1) log(`group of ${batch.length}: ${failing.length} test files fail with all of them broken (${outcome.run.seconds.toFixed(0)} s)`);
    for (const [index, entry] of batch.entries()) {
      const selection = outcome.selections[index] as { selected: Set<string>; everything: boolean };
      const outside = failing.filter((file) => !selection.selected.has(file));
      let missed = outside;
      let own = failing;
      if (batch.length > 1 && outcome.run.fixtureBuildFailed && !selection.everything) {
        const alone = failures(await withMutants(root, [entry.mutant], () => suite(root), cache), baseline);
        missed = alone.filter((file) => !selection.selected.has(file));
        own = alone;
      } else if (batch.length > 1 && outside.length > 0) {
        const alone = await withMutants(root, [entry.mutant], () => suite(root, outside), cache);
        missed = failures(alone, baseline).filter((file) => outside.includes(file));
        own = failing.filter((file) => !outside.includes(file) || missed.includes(file));
      }
      const result = { module: entry.mutant.file, functions: entry.mutant.functions, failing: own, selected: selection.selected.size, everything: selection.everything, missed, seconds: outcome.run.seconds };
      results.push(result);
      log(`${missed.length > 0 ? "MISS" : "ok  "} ${result.module}: ${result.functions} functions broken, ${batch.length > 1 ? "of the failing test files" : ""} ${own.length} ${batch.length > 1 ? "in its selection or failing with it alone" : "fail"}, ${result.everything ? "everything" : `${result.selected} selected`}${missed.length > 0 ? `; not selected: ${missed.join(", ")}` : ""}`);
    }
  }
  return { baseline, results, skipped };
}

export function studyLines(study: Study): string[] {
  const killed = study.results.filter((result) => result.failing.length > 0);
  const missed = study.results.filter((result) => result.missed.length > 0);
  return [
    `mutation study: ${study.results.length} modules broken, ${killed.length} caught by at least one test, ${missed.length} with a failing test outside the selection`,
    ...missed.map((result) => `  ${result.module}: ${result.missed.join(", ")}`),
  ];
}

export function fullSuite(env: NodeJS.ProcessEnv = {}): Suite {
  return async (root, only) => {
    if (root !== repoRoot) throw new Error(`the full suite runs in this repository only, not in ${root}`);
    const results = new Map<string, boolean>();
    const vitest = only?.filter((file) => file.startsWith("test/"));
    const bridge = only?.filter((file) => file.startsWith("bridge/")).map((file) => posix.basename(file));
    const steps = [npmStep("build"), npmStep("build:addon")];
    if (vitest === undefined || vitest.length > 0 || only?.includes(FIXTURE_BUILD) === true) steps.push(npmStep("test", vitest ?? [], env, ["--reporter=./test/setup/progress-reporter.ts"]));
    if (bridge === undefined || bridge.length > 0) steps.push(npmStep("test:bridge", bridge ?? [], env));
    const onFile = (_: string, event: FileEvent): void => {
      const file = posix.normalize(event.file.split("\\").join("/"));
      if (event.event === "end") results.set(file, event.passed !== false);
      else if (!results.has(file)) results.set(file, false);
    };
    const log = timingLogPath("mutation-study");
    const previous = process.env[TIMINGS_VARIABLE];
    process.env[TIMINGS_VARIABLE] = log;
    let run: Awaited<ReturnType<typeof runPhases>>;
    try {
      run = await runPhases([steps], { keepGoing: true, onFile, waitLog: log });
    } finally {
      if (previous === undefined) delete process.env[TIMINGS_VARIABLE];
      else process.env[TIMINGS_VARIABLE] = previous;
    }
    const testStep = run.results.find((result) => /^test(s|$)/.test(result.name));
    const fixtureBuildFailed = testStep !== undefined && !testStep.passed && ![...results.keys()].some((file) => file.startsWith("test/"));
    return { failing: [...results].filter(([, passed]) => !passed).map(([file]) => file).sort(), files: results.size, fixtureBuildFailed, seconds: run.seconds };
  };
}

export function saveStudy(study: Study, path: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(study, null, 2)}\n`);
}
