import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { accepted, type Intent, type IntentKind, type Split } from "./intents.js";

export const BYTES_PER_TOKEN = 2.6;

export type Ranker = (query: string) => string[];

export interface Rate {
  hits: number;
  total: number;
  rate: number;
}

export interface RoutingScore {
  top1: Rate;
  top5: Rate;
  byKind: Record<IntentKind, { top1: Rate; top5: Rate }>;
  misses: { id: string; expected: string[]; got: string[] }[];
  msPerQuery: { mean: number; max: number };
}

export function rate(hits: number, total: number): Rate {
  return { hits, total, rate: total === 0 ? 0 : Math.round((hits / total) * 10000) / 10000 };
}

export function listingBytes(tools: Tool[]): number {
  return Buffer.byteLength(JSON.stringify({ tools }), "utf8");
}

export function estimateTokens(bytes: number): number {
  return Math.round(bytes / BYTES_PER_TOKEN);
}

export function hitAt(intent: Intent, ranked: string[], k: number): boolean {
  const window = ranked.slice(0, Math.max(k, intent.expect.length));
  return intent.expect.every((_, step) => window.some((name) => accepted(intent, step).has(name)));
}

export function firstHit(intent: Intent, ranked: string[]): boolean {
  return ranked[0] !== undefined && accepted(intent, 0).has(ranked[0]);
}

export function scoreRouting(intents: Intent[], rank: Ranker, split?: Split): RoutingScore {
  const chosen = split === undefined ? intents : intents.filter((intent) => intent.split === split);
  const tally = { top1: 0, top5: 0 };
  const kinds: Record<IntentKind, { n: number; top1: number; top5: number }> = { single: { n: 0, top1: 0, top5: 0 }, "near-miss": { n: 0, top1: 0, top5: 0 }, "multi-step": { n: 0, top1: 0, top5: 0 } };
  const misses: RoutingScore["misses"] = [];
  const times: number[] = [];
  for (const intent of chosen) {
    const started = performance.now();
    const ranked = rank(intent.text);
    times.push(performance.now() - started);
    const one = firstHit(intent, ranked);
    const five = hitAt(intent, ranked, 5);
    const kind = kinds[intent.kind];
    kind.n += 1;
    if (one) {
      tally.top1 += 1;
      kind.top1 += 1;
    }
    if (five) {
      tally.top5 += 1;
      kind.top5 += 1;
    } else {
      misses.push({ id: intent.id, expected: intent.expect, got: ranked.slice(0, 5) });
    }
  }
  const byKind = Object.fromEntries(Object.entries(kinds).map(([name, kind]) => [name, { top1: rate(kind.top1, kind.n), top5: rate(kind.top5, kind.n) }])) as RoutingScore["byKind"];
  const mean = times.reduce((sum, time) => sum + time, 0) / Math.max(1, times.length);
  return {
    top1: rate(tally.top1, chosen.length),
    top5: rate(tally.top5, chosen.length),
    byKind,
    misses,
    msPerQuery: { mean: Math.round(mean * 1000) / 1000, max: Math.round(Math.max(0, ...times) * 1000) / 1000 },
  };
}
