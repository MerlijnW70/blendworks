import Anthropic from "@anthropic-ai/sdk";
import { VERSION } from "@anthropic-ai/sdk/version";
import { addUsage, emptyUsage, estimateCost, type Usage } from "./prices.js";
import { EVIDENCE_INTRO } from "./prompt.js";
import { failed, fromText, MAX_OUTPUT_TOKENS, REQUEST_TIMEOUT_MS, type Base, type SampleFailure, type SampleOutcome, type SampleRequest, type VisualProvider } from "./provider.js";

export type CreateParams = Anthropic.Beta.Messages.MessageCreateParamsNonStreaming;
export type Reply = Anthropic.Beta.Messages.BetaMessage;
export type CreateOptions = { timeout: number; maxRetries: number };
export type MessagesClient = { beta: { messages: { create(body: CreateParams, options: CreateOptions): PromiseLike<Reply> } } };

export const FALLBACK_BETA = "server-side-fallback-2026-07-01";
export const MAX_RETRIES = 2;

export function buildRequest(request: SampleRequest, imageData: (index: number) => string = (index) => request.data[index]!.toString("base64")): CreateParams {
  const content: Anthropic.Beta.Messages.BetaContentBlockParam[] = [{ type: "text", text: EVIDENCE_INTRO }];
  request.images.forEach((image, index) => {
    content.push({ type: "text", text: image.caption });
    const last = index === request.images.length - 1;
    content.push({
      type: "image",
      source: { type: "base64", media_type: "image/png", data: imageData(index) },
      ...(last ? { cache_control: { type: "ephemeral" as const } } : {}),
    });
  });
  return {
    model: request.model,
    max_tokens: MAX_OUTPUT_TOKENS,
    betas: [FALLBACK_BETA],
    fallbacks: "default",
    thinking: { type: "adaptive" },
    output_config: { effort: request.effort, format: { type: "json_schema", schema: request.schema } },
    system: [
      { type: "text", text: request.system, cache_control: { type: "ephemeral" } },
      { type: "text", text: request.trusted },
    ],
    messages: [{ role: "user", content }],
  };
}

export function redactedRequest(request: SampleRequest): CreateParams {
  return buildRequest(request, (index) => `sha256:${request.images[index]!.sha256} file:${request.images[index]!.file}`);
}

function replyUsage(reply: Reply): { usage: Usage; cost: number | null } {
  const iterations = reply.usage.iterations ?? [];
  if (iterations.length === 0) {
    const usage = {
      inputTokens: reply.usage.input_tokens,
      outputTokens: reply.usage.output_tokens,
      cacheCreationInputTokens: reply.usage.cache_creation_input_tokens ?? 0,
      cacheReadInputTokens: reply.usage.cache_read_input_tokens ?? 0,
    };
    return { usage, cost: estimateCost(reply.model, usage) };
  }
  let usage = emptyUsage();
  let cost: number | null = 0;
  for (const entry of iterations) {
    const part = { inputTokens: entry.input_tokens, outputTokens: entry.output_tokens, cacheCreationInputTokens: entry.cache_creation_input_tokens, cacheReadInputTokens: entry.cache_read_input_tokens };
    usage = addUsage(usage, part);
    const model = ("model" in entry ? entry.model : null) ?? reply.model;
    const partCost = estimateCost(model, part);
    cost = cost === null || partCost === null ? null : cost + partCost;
  }
  return { usage, cost };
}

export function classifyError(error: unknown): SampleFailure {
  const message = error instanceof Error ? error.message.split("\n")[0]!.slice(0, 300) : String(error);
  if (error instanceof Anthropic.AuthenticationError || error instanceof Anthropic.PermissionDeniedError) return { kind: "not_logged_in", message: `the API refused the credentials: ${message}` };
  if (error instanceof Anthropic.RateLimitError) return { kind: "rate_limited", message: `rate limited after ${MAX_RETRIES} retries: ${message}` };
  if (error instanceof Anthropic.BadRequestError || error instanceof Anthropic.NotFoundError || error instanceof Anthropic.UnprocessableEntityError) return { kind: "rejected", message: `the API rejected the request: ${message}` };
  if (error instanceof Anthropic.APIConnectionTimeoutError) return { kind: "timeout", message: `no reply within ${REQUEST_TIMEOUT_MS / 1000} s` };
  if (error instanceof Anthropic.APIConnectionError) return { kind: "unavailable", message: `cannot reach the API: ${message}` };
  if (error instanceof Anthropic.APIError) return { kind: "api_error", message: `API error ${error.status ?? ""}: ${message}`.replace("  ", " ") };
  if (error instanceof Anthropic.AnthropicError) return { kind: "unavailable", message: `no API credentials: ${message}` };
  throw error;
}

export class AnthropicProvider implements VisualProvider {
  readonly name = "anthropic-api" as const;
  private client: MessagesClient | null;

  constructor(client: MessagesClient | null = null) {
    this.client = client;
  }

  async settings(): Promise<Record<string, unknown>> {
    return { sdk: `@anthropic-ai/sdk ${VERSION}`, timeoutMs: REQUEST_TIMEOUT_MS, maxRetries: MAX_RETRIES, betas: [FALLBACK_BETA], fallbacks: "default" };
  }

  describeRequest(request: SampleRequest): unknown {
    return redactedRequest(request);
  }

  async score(request: SampleRequest): Promise<SampleOutcome> {
    const body = buildRequest(request);
    const base: Base = { servedBy: null, stopReason: null, stopDetails: null, usage: emptyUsage(), costUsd: null, costSource: null, meta: {} };
    let reply: Reply;
    try {
      this.client ??= new Anthropic();
      reply = await this.client.beta.messages.create(body, { timeout: REQUEST_TIMEOUT_MS, maxRetries: MAX_RETRIES });
    } catch (error) {
      return failed(base, classifyError(error));
    }
    const { usage, cost } = replyUsage(reply);
    const served: Base = {
      ...base,
      servedBy: reply.model,
      stopReason: reply.stop_reason,
      stopDetails: reply.stop_details ?? null,
      usage,
      costUsd: cost,
      costSource: cost === null ? null : "price-table",
      meta: { id: reply.id, fallback: (reply.usage.iterations ?? []).some((entry) => entry.type === "fallback_message") },
    };
    if (reply.stop_reason === "refusal") {
      const category = reply.stop_details?.category ?? "no category";
      return failed(served, { kind: "refused", message: `the model declined (${category})` });
    }
    if (reply.stop_reason === "max_tokens") return failed(served, { kind: "malformed", message: `the reply stopped at ${MAX_OUTPUT_TOKENS} output tokens` });
    const text = reply.content.flatMap((block) => (block.type === "text" ? [block.text] : [])).join("");
    return fromText(served, request.rubric, text === "" ? null : text);
  }
}
