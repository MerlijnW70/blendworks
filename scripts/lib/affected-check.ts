import { blenderJobs } from "../../src/blender.js";
import { discoverTests, gitChanges, mergeBase, type Selection, selectAffected, workingRepo } from "./affected.js";
import { npmStep, type Step } from "./pipeline.js";

export type AffectedArgs = { base: string | undefined; dryRun: boolean };

export function parseAffectedArgs(argv: string[]): AffectedArgs | string {
  const out: AffectedArgs = { base: undefined, dryRun: false };
  for (let at = 0; at < argv.length; at += 1) {
    const argument = argv[at] as string;
    if (argument === "--base") {
      const value = argv[at + 1];
      if (value === undefined || value.startsWith("-")) return "--base needs a git ref, such as --base main";
      out.base = value;
      at += 1;
    } else if (argument === "--dry-run") out.dryRun = true;
    else return `unknown argument ${argument}; usage: npm run check:affected -- [--base <ref>] [--dry-run]`;
  }
  return out;
}

export function affectedPhases(selection: Selection, vitestReporters: string[]): Step[][] {
  const steps: Step[] = [npmStep("rules"), npmStep("typecheck"), npmStep("build"), npmStep("build:addon"), npmStep("test", selection.everything ? [] : selection.vitest, selection.fixtures ? {} : { BLENDWORKS_FIXTURES: "skip" }, vitestReporters)];
  if (selection.everything || selection.bridge.length > 0) steps.push(npmStep("test:bridge", selection.everything ? [] : selection.bridge.map((file) => file.split("/").pop() as string)));
  return [steps];
}

export function selectionLines(base: string, selection: Selection, blender: Set<string>): string[] {
  const lines = [`changed against ${base.slice(0, 12)}: ${selection.byChange.size === 0 && selection.reasons.length === 0 ? "nothing" : `${selection.reasons.length} files`}`];
  for (const reason of selection.reasons) lines.push(`  ${reason}`);
  if (selection.everything) lines.push("selection: everything (the full check's tests)");
  else {
    const heavy = selection.vitest.filter((file) => blender.has(file));
    lines.push(`selection: ${selection.vitest.length - heavy.length} unit test files that need no Blender (always), ${heavy.length} vitest files with Blender, ${selection.bridge.length} bridge test files; core set ${["smoke", "contract"].join(" and ")} tests included${selection.fixtures ? "; the judge fixtures are built" : ""}`);
    if (heavy.length > 0) lines.push(`  Blender vitest: ${heavy.join(", ")}`);
    if (selection.bridge.length > 0) lines.push(`  bridge: ${selection.bridge.map((file) => file.split("/").pop()).join(", ")}`);
  }
  lines.push(`Blender slots: ${blenderJobs()}`);
  return lines;
}

export function chooseAffected(args: AffectedArgs): { base: string; selection: Selection; blender: Set<string> } {
  const base = mergeBase(args.base);
  const repo = workingRepo(base);
  const selection = selectAffected(gitChanges(base), repo);
  return { base, selection, blender: new Set(discoverTests(repo.source).blender) };
}
