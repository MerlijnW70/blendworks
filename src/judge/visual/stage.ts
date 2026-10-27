import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { AnthropicProvider, type MessagesClient } from "./anthropic.js";
import { ClaudeCodeProvider } from "./claude-code.js";
import { IMAGE_CAP, prepareEvidence, sha256Of, type Evidence, type EvidenceSource } from "./images.js";
import { addUsage, emptyUsage, PRICES_AS_OF } from "./prices.js";
import type { Spawner } from "./process.js";
import { instructionLike, outputSchema, SYSTEM_PROMPT, trustedBlock, type Answer } from "./prompt.js";
import { apiCredentialsResolve, chooseProvider, FATAL_FAILURES, type ProviderChoice, type SampleOutcome, type SampleRequest, type VisualProvider } from "./provider.js";
import { COMMITTEE_TEXT, RECORD_VERSION, SCORE_RULE, type InjectionFinding, type SampleRecord, type VisualRecord, type VisualRequestRecord } from "./record.js";
import { criterionScores, overallScore, quorum } from "./score.js";
import { resolveRule, type ResolvedRule, type VisualRule } from "./spec.js";

export type VisualOptions = {
  provider?: VisualProvider;
  anthropicClient?: MessagesClient;
  spawn?: Spawner;
  env?: NodeJS.ProcessEnv;
  credentials?: () => Promise<boolean>;
  imageCap?: number;
  closeupResolution?: number;
  closeupSamples?: number;
};

export type VisualInput = { rule: VisualRule; brief: string; sources: EvidenceSource[]; outDir: string; options: VisualOptions };

const CONCURRENCY: Record<string, number> = { "anthropic-api": 4, "claude-code": 2 };

function ruleText(resolved: ResolvedRule): string {
  return resolved.models.length > 1 ? `${SCORE_RULE}; ${COMMITTEE_TEXT[resolved.committee]}` : SCORE_RULE;
}

export function baseRecord(rule: VisualRule, env: NodeJS.ProcessEnv): VisualRecord {
  let resolved: ResolvedRule | null = null;
  try {
    resolved = resolveRule(rule, env);
  } catch {
    resolved = null;
  }
  return {
    version: RECORD_VERSION,
    status: "inconclusive",
    required: rule.required ?? false,
    reason: null,
    score: null,
    minScore: resolved?.minScore ?? rule.minScore ?? 0.7,
    rule: resolved ? ruleText(resolved) : SCORE_RULE,
    rubric: rule.rubric,
    criteria: null,
    injection: { flagged: false, findings: [] },
    request: null,
    images: [],
    samples: [],
    usage: emptyUsage(),
    costUsd: null,
    costNote: `estimated from the list prices of ${PRICES_AS_OF}; the claude-code provider reports its own list-price figure, which counts against the subscription's usage limits rather than being billed`,
  };
}

export function inconclusive(rule: VisualRule, env: NodeJS.ProcessEnv, reason: string): VisualRecord {
  return { ...baseRecord(rule, env), reason };
}

function makeProvider(choice: ProviderChoice, options: VisualOptions, env: NodeJS.ProcessEnv): VisualProvider {
  if (options.provider !== undefined) return options.provider;
  return choice.name === "anthropic-api" ? new AnthropicProvider(options.anthropicClient ?? null) : new ClaudeCodeProvider(options.spawn, env);
}

async function pooled<T>(count: number, limit: number, task: () => Promise<T>): Promise<T[]> {
  const results: T[] = [];
  let next = 0;
  const worker = async () => {
    while (next < count) {
      next += 1;
      results.push(await task());
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, count) }, worker));
  return results;
}

async function sampleModel(provider: VisualProvider, request: SampleRequest, samples: number): Promise<SampleOutcome[]> {
  const first = await provider.score(request);
  if (samples === 1 || (first.failure !== null && FATAL_FAILURES.includes(first.failure.kind))) return [first];
  return [first, ...(await pooled(samples - 1, CONCURRENCY[provider.name] ?? 1, () => provider.score(request)))];
}

function findings(samples: SampleRecord[]): InjectionFinding[] {
  return samples.flatMap((sample) => {
    if (sample.answer === null) return [];
    const found: InjectionFinding[] = [];
    if (sample.answer.injectionAttempt) found.push({ model: sample.model, sample: sample.index, source: "model", text: sample.answer.injectionEvidence || "flagged without a description" });
    for (const text of instructionLike(sample.answer.visibleText)) found.push({ model: sample.model, sample: sample.index, source: "transcript", text });
    return found;
  });
}

function decide(record: VisualRecord, resolved: ResolvedRule): Pick<VisualRecord, "status" | "reason"> {
  const { findings: found } = record.injection;
  if (found.length > 0) return { status: "inconclusive", reason: `instruction-like text in the renders (${found.length} findings), first: ${found[0]!.text}` };
  const refused = record.samples.find((sample) => sample.status === "refused");
  if (refused) return { status: "inconclusive", reason: `${refused.model} declined to score: ${refused.failure?.message ?? "refusal"}` };
  const needed = quorum(resolved.samples);
  for (const model of resolved.models) {
    const answered = record.samples.filter((sample) => sample.model === model && sample.status === "ok").length;
    if (answered < needed) {
      const failure = record.samples.find((sample) => sample.model === model && sample.failure !== null)?.failure;
      return { status: "inconclusive", reason: `only ${answered} of ${resolved.samples} samples from ${model} answered, ${needed} needed${failure ? `: ${failure.message}` : ""}` };
    }
  }
  if (record.score === null) return { status: "inconclusive", reason: "no score" };
  return record.score >= resolved.minScore ? { status: "pass", reason: null } : { status: "fail", reason: null };
}

function requestRecord(resolved: ResolvedRule, choice: ProviderChoice, settings: Record<string, unknown>, system: string, trusted: string, schema: Record<string, unknown>, cap: number): VisualRequestRecord {
  return {
    provider: choice.name,
    providerSource: choice.source,
    providerSettings: settings,
    models: resolved.models,
    modelSource: resolved.modelSource,
    effort: resolved.effort,
    samples: resolved.samples,
    quorum: quorum(resolved.samples),
    committee: resolved.models.length > 1 ? resolved.committee : null,
    imageCap: cap,
    system,
    systemSha256: sha256Of(system),
    trusted,
    trustedSha256: sha256Of(trusted),
    schema,
    calls: {},
  };
}

export async function scoreVisual(input: VisualInput): Promise<VisualRecord> {
  const env = input.options.env ?? process.env;
  const record = baseRecord(input.rule, env);
  const resolved = resolveRule(input.rule, env);
  const cap = input.options.imageCap ?? IMAGE_CAP;
  const evidence: Evidence = prepareEvidence(input.sources, input.outDir, cap);
  record.images = evidence.images;
  const choice = input.options.provider ? { name: input.options.provider.name, source: "spec" as const } : await chooseProvider(input.rule, env, input.options.credentials ?? (() => apiCredentialsResolve(env)));
  const provider = makeProvider(choice, input.options, env);
  const trusted = trustedBlock(input.brief, resolved.rubric);
  const schema = outputSchema(resolved.rubric);
  record.request = requestRecord(resolved, choice, await provider.settings(), SYSTEM_PROMPT, trusted, schema, cap);
  for (const model of resolved.models) {
    const request: SampleRequest = { model, effort: resolved.effort, system: SYSTEM_PROMPT, trusted, schema, rubric: resolved.rubric, images: evidence.images, data: evidence.data };
    record.request.calls[model] = provider.describeRequest(request);
    const outcomes = await sampleModel(provider, request, resolved.samples);
    record.samples.push(...outcomes.map((outcome, index): SampleRecord => ({ model, index, ...outcome })));
  }
  record.usage = record.samples.reduce((sum, sample) => addUsage(sum, sample.usage), emptyUsage());
  record.costUsd = record.samples.some((sample) => sample.costUsd === null && sample.status !== "error") ? null : record.samples.reduce((sum, sample) => sum + (sample.costUsd ?? 0), 0);
  record.injection = { flagged: false, findings: findings(record.samples) };
  record.injection.flagged = record.injection.findings.length > 0;
  const answers: Record<string, Answer[]> = Object.fromEntries(resolved.models.map((model) => [model, record.samples.filter((sample) => sample.model === model && sample.answer !== null).map((sample) => sample.answer!)]));
  record.criteria = criterionScores(resolved.rubric, answers, resolved.committee);
  record.score = record.criteria === null ? null : overallScore(resolved.rubric, record.criteria);
  Object.assign(record, decide(record, resolved));
  return record;
}

export function writeVisualRecord(outDir: string, record: VisualRecord): void {
  writeFileSync(join(outDir, "visual.json"), `${JSON.stringify(record, null, 2)}\n`);
}
