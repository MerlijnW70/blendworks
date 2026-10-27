export type Usage = { inputTokens: number; outputTokens: number; cacheCreationInputTokens: number; cacheReadInputTokens: number };

export type Price = { input: number; output: number; cacheWrite: number; cacheRead: number };

export const PRICES_AS_OF = "2026-10";

export const PRICES_PER_MILLION: Record<string, Price> = {
  "claude-fable-5-1": { input: 10, output: 50, cacheWrite: 12.5, cacheRead: 0.25 },
  "claude-opus-5-5": { input: 4, output: 20, cacheWrite: 5, cacheRead: 0.2 },
  "claude-opus-5": { input: 5, output: 25, cacheWrite: 6.25, cacheRead: 0.5 },
  "claude-opus-4-8": { input: 5, output: 25, cacheWrite: 6.25, cacheRead: 0.5 },
  "claude-sonnet-5-5": { input: 2, output: 10, cacheWrite: 2.5, cacheRead: 0.2 },
  "claude-haiku-5-5": { input: 0.1, output: 0.5, cacheWrite: 0.125, cacheRead: 0.01 },
};

export function emptyUsage(): Usage {
  return { inputTokens: 0, outputTokens: 0, cacheCreationInputTokens: 0, cacheReadInputTokens: 0 };
}

export function addUsage(into: Usage, more: Usage): Usage {
  return {
    inputTokens: into.inputTokens + more.inputTokens,
    outputTokens: into.outputTokens + more.outputTokens,
    cacheCreationInputTokens: into.cacheCreationInputTokens + more.cacheCreationInputTokens,
    cacheReadInputTokens: into.cacheReadInputTokens + more.cacheReadInputTokens,
  };
}

export function estimateCost(model: string, usage: Usage): number | null {
  const price = PRICES_PER_MILLION[model];
  if (price === undefined) return null;
  const dollars =
    usage.inputTokens * price.input + usage.outputTokens * price.output + usage.cacheCreationInputTokens * price.cacheWrite + usage.cacheReadInputTokens * price.cacheRead;
  return dollars / 1_000_000;
}
