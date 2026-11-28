import { join } from "node:path";
import { repoSource } from "./dep-graph.js";
import { chooseModules, fullSuite, runStudy, saveStudy, studyLines } from "./mutation-study.js";
import { cacheRoot, repoRoot } from "./paths.js";

export const DEFAULT_COUNT = 30;

function option(argv: string[], name: string): string | undefined {
  const at = argv.indexOf(name);
  return at >= 0 ? argv[at + 1] : undefined;
}

export async function studyMain(argv: string[]): Promise<number> {
  const source = repoSource();
  const listed = option(argv, "--modules");
  const count = Number(option(argv, "--count") ?? DEFAULT_COUNT);
  const modules = listed !== undefined ? listed.split(",").filter((item) => item !== "") : chooseModules(source.files, count, source.read);
  console.log(`breaking ${modules.length} modules, one at a time, and running the full suite for each: ${modules.join(", ")}`);
  if (argv.includes("--list")) return 0;
  const study = await runStudy(repoRoot, modules, fullSuite(), { group: Number(option(argv, "--group") ?? 1) });
  const out = option(argv, "--out") ?? join(cacheRoot(), "mutation-study.json");
  saveStudy(study, out);
  for (const line of studyLines(study)) console.log(line);
  console.log(`results: ${out}`);
  return study.results.some((result) => result.missed.length > 0) ? 1 : 0;
}
