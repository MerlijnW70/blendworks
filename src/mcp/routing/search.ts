import { type Bm25Options, Bm25Index, type Ranked, type WeightedField } from "./bm25.js";
import type { Route } from "./catalog.js";
import { PYTHON_TOOL, toolNameOf } from "./names.js";
import { expand } from "./synonyms.js";
import { tokens, words } from "./text.js";
import { WORKFLOWS, type Workflow } from "./workflows.js";

export interface FieldWeights {
  name: number;
  family: number;
  summary: number;
  intents: number;
  parameters: number;
  pointers: number;
  synonyms: number;
}

export const DEFAULT_WEIGHTS: FieldWeights = { name: 3, family: 1, summary: 1, intents: 3, parameters: 0.5, pointers: 1, synonyms: 0.3 };

export const ROUTER_BM25: Bm25Options = { k1: 0.9, b: 0.5 };

export interface SearchOptions {
  limit?: number;
  families?: string[];
}

export interface Match {
  name: string;
  score: number;
}

const IGNORED_PARAMETERS = new Set(["timeout_seconds", "name", "names"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function enumWords(schema: unknown, depth: number): string[] {
  if (!isRecord(schema) || depth > 2) return [];
  const own = Array.isArray(schema["enum"]) ? schema["enum"].filter((value): value is string => typeof value === "string") : [];
  const items = enumWords(schema["items"], depth + 1);
  return [...own, ...items];
}

export function parameterText(route: Route): string {
  const properties = isRecord(route.tool.inputSchema.properties) ? route.tool.inputSchema.properties : {};
  const parts: string[] = [];
  for (const [field, schema] of Object.entries(properties)) {
    if (IGNORED_PARAMETERS.has(field)) continue;
    parts.push(field.replace(/_/g, " "), ...enumWords(schema, 0).map((value) => value.replace(/_/g, " ")));
  }
  return parts.join(" ");
}

function bareName(name: string): string {
  return name.replace(/^(blender|library)_/, "").replace(/_/g, " ");
}

export const LAST_RESORT_RANK = 2;

export function lastResortAfter(ranked: Ranked[]): Ranked[] {
  const index = ranked.findIndex((entry) => entry.key === PYTHON_TOOL);
  if (index < 0 || index >= LAST_RESORT_RANK) return ranked;
  const others = ranked.filter((entry) => entry.key !== PYTHON_TOOL);
  return [...others.slice(0, LAST_RESORT_RANK), ranked[index]!, ...others.slice(LAST_RESORT_RANK)];
}

export class ToolSearch {
  private readonly index: Bm25Index;
  private readonly goals: Bm25Index;
  private readonly families: Map<string, string>;

  constructor(
    readonly routes: Route[],
    private readonly weights: FieldWeights = DEFAULT_WEIGHTS,
    options: Bm25Options = ROUTER_BM25,
    readonly workflows: Workflow[] = WORKFLOWS,
  ) {
    this.index = new Bm25Index(options);
    this.families = new Map(routes.map((route) => [route.name, route.family]));
    const pointers = new Map<string, string[]>();
    for (const route of routes) {
      for (const entry of route.nearest) {
        const target = toolNameOf(entry.name);
        pointers.set(target, [...(pointers.get(target) ?? []), entry.when]);
      }
    }
    for (const route of routes) {
      const fields: WeightedField[] = [
        { tokens: tokens(bareName(route.name)), weight: weights.name },
        { tokens: tokens(route.family.replace(/_/g, " ")), weight: weights.family },
        { tokens: tokens(route.summary), weight: weights.summary },
        { tokens: tokens(route.intents.join(" ")), weight: weights.intents },
        { tokens: tokens(parameterText(route)), weight: weights.parameters },
        { tokens: tokens((pointers.get(route.name) ?? []).join(" ")), weight: weights.pointers },
      ];
      this.index.add(route.name, fields);
    }
    this.goals = new Bm25Index(options);
    for (const workflow of workflows) {
      this.goals.add(workflow.id, [
        { tokens: tokens(workflow.goal), weight: 3 },
        { tokens: tokens(workflow.examples.join(" ")), weight: 2 },
        { tokens: tokens(workflow.steps.map(bareName).join(" ")), weight: 1 },
      ]);
    }
  }

  query(text: string): Map<string, number> {
    const bag = new Map<string, number>();
    for (const token of tokens(text)) bag.set(token, 1);
    for (const word of expand(words(text))) {
      for (const token of tokens(word)) if (!bag.has(token)) bag.set(token, this.weights.synonyms);
    }
    return bag;
  }

  search(text: string, options: SearchOptions = {}): Match[] {
    const families = options.families === undefined || options.families.length === 0 ? undefined : new Set(options.families);
    const ranked = lastResortAfter(this.index.score(this.query(text), families === undefined ? undefined : (key) => families.has(this.families.get(key) ?? "")));
    return ranked.slice(0, options.limit ?? ranked.length).map((entry: Ranked) => ({ name: entry.key, score: Math.round(entry.score * 1000) / 1000 }));
  }

  goal(text: string): { workflow: Workflow; score: number } | undefined {
    const best = this.goals.score(this.query(text))[0];
    if (best === undefined) return undefined;
    const workflow = this.workflows.find((entry) => entry.id === best.key);
    return workflow === undefined ? undefined : { workflow, score: Math.round(best.score * 1000) / 1000 };
  }
}
