import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, sep } from "node:path";
import { repoRoot } from "./paths.js";
import type { Timing } from "./timings.js";

export type Outcome = "passed" | "failed" | "skipped";

export type PassList = { files: Record<string, Outcome>; tests: Record<string, Outcome> };

type VitestJson = { testResults?: { name?: string; status?: string; assertionResults?: { fullName?: string; status?: string }[] }[] };

function outcome(status: string | undefined): Outcome {
  if (status === "passed") return "passed";
  if (status === "failed") return "failed";
  return "skipped";
}

function key(path: string): string {
  return relative(repoRoot, path).split(sep).join("/");
}

export function vitestPassList(report: VitestJson): PassList {
  const list: PassList = { files: {}, tests: {} };
  for (const file of report.testResults ?? []) {
    if (file.name === undefined) continue;
    const name = key(file.name);
    const tests = file.assertionResults ?? [];
    for (const test of tests) list.tests[`${name} > ${test.fullName ?? "?"}`] = outcome(test.status);
    const outcomes = tests.map((test) => outcome(test.status));
    list.files[name] = file.status === "failed" || outcomes.includes("failed") ? "failed" : outcomes.length > 0 && outcomes.every((entry) => entry === "skipped") ? "skipped" : outcome(file.status);
  }
  return list;
}

export function readVitestPassList(path: string): PassList {
  try {
    return vitestPassList(JSON.parse(readFileSync(path, "utf8")) as VitestJson);
  } catch {
    return { files: {}, tests: {} };
  }
}

export const BRIDGE_STAGE = "test:bridge";

export function bridgePassList(timings: Timing[], stage: string = BRIDGE_STAGE): PassList {
  const list: PassList = { files: {}, tests: {} };
  for (const timing of timings) {
    if (timing.kind !== "result" || timing.stage !== stage) continue;
    list.files[timing.file] = timing.passed ? "passed" : "failed";
    for (const test of timing.tests) list.tests[`${timing.file} > ${test.name}`] = test.passed ? "passed" : "failed";
  }
  return list;
}

export function mergePassLists(...lists: PassList[]): PassList {
  const sorted = (entries: Record<string, Outcome>[]): Record<string, Outcome> => Object.fromEntries(entries.flatMap((entry) => Object.entries(entry)).sort((a, b) => a[0].localeCompare(b[0])));
  return { files: sorted(lists.map((list) => list.files)), tests: sorted(lists.map((list) => list.tests)) };
}

export function passListDigest(list: PassList): string {
  return createHash("sha256").update(JSON.stringify(list)).digest("hex");
}

function counts(entries: Record<string, Outcome>): string {
  const values = Object.values(entries);
  const count = (wanted: Outcome) => values.filter((value) => value === wanted).length;
  return `${count("passed")} passed, ${count("failed")} failed, ${count("skipped")} skipped`;
}

export function passListLines(list: PassList, path: string): string[] {
  return [`pass list: files ${counts(list.files)}; tests ${counts(list.tests)}; sha256 ${passListDigest(list)} (${path})`];
}

export function writePassList(list: PassList, path: string): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(list, null, 1)}\n`);
}

export type PassListChange = { file: string; before: Outcome | undefined; after: Outcome | undefined };

export function comparePassLists(before: PassList, after: PassList): PassListChange[] {
  const changes: PassListChange[] = [];
  for (const kind of ["files", "tests"] as const) {
    const names = new Set([...Object.keys(before[kind]), ...Object.keys(after[kind])]);
    for (const name of [...names].sort()) if (before[kind][name] !== after[kind][name]) changes.push({ file: name, before: before[kind][name], after: after[kind][name] });
  }
  return changes;
}
