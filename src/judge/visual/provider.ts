import { loadConfig, loadCredentials } from "@anthropic-ai/sdk/core/credentials";
import type { EvidenceImage } from "./images.js";
import type { Usage } from "./prices.js";
import { validateAnswer, type Answer } from "./prompt.js";
import { PROVIDERS, type Criterion, type Effort, type ProviderName, type VisualRule } from "./spec.js";

export const PROVIDER_VARIABLE = "BLENDWORKS_VLM_PROVIDER";
export const REQUEST_TIMEOUT_MS = 300_000;
export const MAX_OUTPUT_TOKENS = 16_000;

export type SampleRequest = {
  model: string;
  effort: Effort;
  system: string;
  trusted: string;
  schema: Record<string, unknown>;
  rubric: Criterion[];
  images: EvidenceImage[];
  data: Buffer[];
};

export type FailureKind = "unavailable" | "not_logged_in" | "rate_limited" | "timeout" | "rejected" | "api_error" | "not_isolated" | "malformed" | "refused";

export type SampleFailure = { kind: FailureKind; message: string };

export type SampleOutcome = {
  status: "ok" | "malformed" | "refused" | "error";
  answer: Answer | null;
  failure: SampleFailure | null;
  servedBy: string | null;
  stopReason: string | null;
  stopDetails: unknown;
  usage: Usage;
  costUsd: number | null;
  costSource: "price-table" | "provider" | null;
  raw: string | null;
  meta: Record<string, unknown>;
};

export interface VisualProvider {
  readonly name: ProviderName;
  settings(): Promise<Record<string, unknown>>;
  describeRequest(request: SampleRequest): unknown;
  score(request: SampleRequest): Promise<SampleOutcome>;
}

export const FATAL_FAILURES: readonly FailureKind[] = ["unavailable", "not_logged_in", "rejected", "not_isolated"];

export type Base = Omit<SampleOutcome, "status" | "answer" | "failure" | "raw">;

export function failed(base: Base, failure: SampleFailure, raw: string | null = null): SampleOutcome {
  const status = failure.kind === "refused" ? "refused" : failure.kind === "malformed" ? "malformed" : "error";
  return { ...base, status, answer: null, failure, raw };
}

export function fromValue(base: Base, rubric: Criterion[], value: unknown, raw: string | null): SampleOutcome {
  const checked = validateAnswer(rubric, value);
  if (!checked.ok) return failed(base, { kind: "malformed", message: `the reply does not match the schema: ${checked.problem}` }, raw);
  return { ...base, status: "ok", answer: checked.answer, failure: null, raw: null };
}

export function fromText(base: Base, rubric: Criterion[], text: string | null): SampleOutcome {
  if (text === null) return failed(base, { kind: "malformed", message: "the reply has no text" });
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return failed(base, { kind: "malformed", message: "the reply is not JSON" }, text.slice(0, 4000));
  }
  return fromValue(base, rubric, value, text.slice(0, 4000));
}

export async function apiCredentialsResolve(env: NodeJS.ProcessEnv = process.env): Promise<boolean> {
  if (env.ANTHROPIC_API_KEY || env.ANTHROPIC_AUTH_TOKEN || env.ANTHROPIC_PROFILE) return true;
  if (env.ANTHROPIC_FEDERATION_RULE_ID && env.ANTHROPIC_ORGANIZATION_ID && (env.ANTHROPIC_IDENTITY_TOKEN || env.ANTHROPIC_IDENTITY_TOKEN_FILE)) return true;
  try {
    const config = await loadConfig();
    if (config === null) return false;
    if (config.authentication.type === "oidc_federation") return true;
    return (await loadCredentials()) !== null;
  } catch {
    return false;
  }
}

export type ProviderChoice = { name: ProviderName; source: "environment" | "spec" | "api-credentials" | "no-api-credentials" };

export async function chooseProvider(rule: VisualRule, env: NodeJS.ProcessEnv, credentials: () => Promise<boolean>): Promise<ProviderChoice> {
  const fromEnv = env[PROVIDER_VARIABLE]?.trim();
  if (fromEnv) {
    if (!(PROVIDERS as readonly string[]).includes(fromEnv)) throw new Error(`${PROVIDER_VARIABLE} must be ${PROVIDERS.join(" or ")}, not ${JSON.stringify(fromEnv)}`);
    return { name: fromEnv as ProviderName, source: "environment" };
  }
  if (rule.provider !== undefined) return { name: rule.provider, source: "spec" };
  return (await credentials()) ? { name: "anthropic-api", source: "api-credentials" } : { name: "claude-code", source: "no-api-credentials" };
}
