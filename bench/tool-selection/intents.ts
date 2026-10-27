import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export type IntentKind = "single" | "near-miss" | "multi-step";
export type Split = "tune" | "heldout" | "probe";

export interface Intent {
  id: string;
  text: string;
  kind: IntentKind;
  split: Split;
  expect: string[];
  alternatives?: string[];
  confusable?: string;
}

export const INTENTS_FILE = fileURLToPath(new URL("./intents.json", import.meta.url));

export function loadIntents(file: string = INTENTS_FILE): Intent[] {
  const intents = JSON.parse(readFileSync(file, "utf8")) as Intent[];
  const ids = new Set<string>();
  for (const intent of intents) {
    if (ids.has(intent.id)) throw new Error(`intent id ${intent.id} is used twice`);
    ids.add(intent.id);
    if (intent.expect.length === 0) throw new Error(`intent ${intent.id} expects no tool`);
    if (intent.kind === "near-miss" && intent.confusable === undefined) throw new Error(`near-miss intent ${intent.id} names no confusable tool`);
  }
  return intents;
}

export function accepted(intent: Intent, step: number): Set<string> {
  const names = new Set([intent.expect[step]!]);
  if (step === 0) for (const name of intent.alternatives ?? []) names.add(name);
  return names;
}

export function missingTools(intents: Intent[], tools: string[]): { unknown: string[]; uncovered: string[] } {
  const named = new Set(intents.flatMap((intent) => [...intent.expect, ...(intent.alternatives ?? []), ...(intent.confusable === undefined ? [] : [intent.confusable])]));
  const listed = new Set(tools);
  const expected = new Set(intents.flatMap((intent) => intent.expect));
  return {
    unknown: [...named].filter((name) => !listed.has(name)).sort(),
    uncovered: tools.filter((name) => !expected.has(name)).sort(),
  };
}
