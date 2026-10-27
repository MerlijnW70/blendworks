import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { emptyUsage, type Usage } from "./prices.js";
import { EVIDENCE_INTRO } from "./prompt.js";
import { failed, fromValue, REQUEST_TIMEOUT_MS, type Base, type SampleFailure, type SampleOutcome, type SampleRequest, type VisualProvider } from "./provider.js";
import { findClaude, runProcess, type Run, type Spawner } from "./process.js";

export const MAX_TURNS = 3;
export const MAX_BUDGET_USD = 2;
export const ALLOWED_TOOLS = ["StructuredOutput"];

export function claudeArgs(request: SampleRequest): string[] {
  return [
    "--print",
    "--input-format",
    "stream-json",
    "--output-format",
    "stream-json",
    "--verbose",
    "--safe-mode",
    "--restricted",
    "--setting-sources",
    "",
    "--strict-mcp-config",
    "--tools",
    "",
    "--disable-slash-commands",
    "--permission-mode",
    "dontAsk",
    "--no-session-persistence",
    "--max-turns",
    String(MAX_TURNS),
    "--max-budget-usd",
    String(MAX_BUDGET_USD),
    "--model",
    request.model,
    "--effort",
    request.effort,
    "--system-prompt",
    `${request.system}\n\n${request.trusted}`,
    "--json-schema",
    JSON.stringify(request.schema),
  ];
}

export function claudeInput(request: SampleRequest, imageData: (index: number) => string = (index) => request.data[index]!.toString("base64")): string {
  const content: unknown[] = [{ type: "text", text: EVIDENCE_INTRO }];
  request.images.forEach((image, index) => {
    content.push({ type: "text", text: image.caption });
    content.push({ type: "image", source: { type: "base64", media_type: "image/png", data: imageData(index) } });
  });
  return `${JSON.stringify({ type: "user", message: { role: "user", content } })}\n`;
}

export function childEnvironment(env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return Object.fromEntries(Object.entries(env).filter(([name]) => !/^CLAUDE/i.test(name) || name.toUpperCase() === "CLAUDE_CONFIG_DIR"));
}

type Event = Record<string, unknown>;

function events(stdout: string): Event[] {
  return stdout.split("\n").flatMap((line) => {
    if (!line.trim().startsWith("{")) return [];
    try {
      const value: unknown = JSON.parse(line);
      return value !== null && typeof value === "object" ? [value as Event] : [];
    } catch {
      return [];
    }
  });
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

function resultUsage(result: Event): Usage {
  const usage = (result.usage ?? {}) as Record<string, unknown>;
  if (typeof usage !== "object") return emptyUsage();
  return {
    inputTokens: count(usage.input_tokens),
    outputTokens: count(usage.output_tokens),
    cacheCreationInputTokens: count(usage.cache_creation_input_tokens),
    cacheReadInputTokens: count(usage.cache_read_input_tokens),
  };
}

export function isolationProblem(init: Event | undefined): string | null {
  if (init === undefined) return "the CLI did not report its session";
  const tools = Array.isArray(init.tools) ? init.tools : null;
  if (tools === null || tools.some((tool) => !ALLOWED_TOOLS.includes(String(tool)))) return `the CLI session has tools ${JSON.stringify(init.tools)}, only ${ALLOWED_TOOLS.join(", ")} is allowed`;
  for (const field of ["mcp_servers", "skills", "slash_commands"]) {
    const value = init[field];
    if (!Array.isArray(value) || value.length > 0) return `the CLI session loaded ${field} ${JSON.stringify(value)}`;
  }
  return null;
}

function errorFailure(result: Event): SampleFailure {
  const text = typeof result.result === "string" ? result.result.slice(0, 300) : "";
  const status = typeof result.api_error_status === "number" ? result.api_error_status : null;
  const subtype = String(result.subtype ?? "error");
  if (status === 401 || status === 403 || /not logged in|\/login|invalid api key|authenticat|oauth/i.test(text)) return { kind: "not_logged_in", message: `the claude CLI is not logged in: ${text}` };
  if (status === 429 || /rate.?limit|usage limit|limit reached/i.test(text)) return { kind: "rate_limited", message: `the claude CLI is rate limited: ${text}` };
  if (subtype === "error_max_turns") return { kind: "malformed", message: `the reply took more than ${MAX_TURNS} turns` };
  if (subtype === "error_max_budget_usd") return { kind: "rejected", message: `the reply cost more than ${MAX_BUDGET_USD} USD` };
  return { kind: "api_error", message: `the claude CLI reported ${subtype}${status === null ? "" : ` (${status})`}: ${text}` };
}

export function parseRun(run: Run, request: SampleRequest): SampleOutcome {
  const base: Base = { servedBy: null, stopReason: null, stopDetails: null, usage: emptyUsage(), costUsd: null, costSource: null, meta: {} };
  if (run.missing) return failed(base, { kind: "unavailable", message: "the claude CLI is not installed or not on PATH" });
  if (run.timedOut) return failed(base, { kind: "timeout", message: `no reply within ${REQUEST_TIMEOUT_MS / 1000} s` });
  const all = events(run.stdout);
  const init = all.find((event) => event.type === "system" && event.subtype === "init");
  const result = [...all].reverse().find((event) => event.type === "result");
  const limited = all.find((event) => event.type === "rate_limit_event" && (event.rate_limit_info as Event | undefined)?.status === "rejected");
  const meta = { cli: init ? { version: init.claude_code_version ?? null, model: init.model ?? null, tools: init.tools ?? null, permissionMode: init.permissionMode ?? null, apiKeySource: init.apiKeySource ?? null } : null };
  const problem = isolationProblem(init);
  if (result === undefined) {
    if (limited) return failed({ ...base, meta }, { kind: "rate_limited", message: "the claude CLI is rate limited" });
    if (init !== undefined && problem !== null) return failed({ ...base, meta }, { kind: "not_isolated", message: problem });
    const tail = run.stderr.trim().split("\n").slice(-3).join(" ").slice(0, 300);
    return failed({ ...base, meta }, { kind: "api_error", message: `the claude CLI exited with ${run.code} and no result${tail ? `: ${tail}` : ""}` });
  }
  const modelUsage = (result.modelUsage ?? {}) as Record<string, unknown>;
  const cost = typeof result.total_cost_usd === "number" ? result.total_cost_usd : null;
  const served: Base = {
    ...base,
    servedBy: Object.keys(modelUsage)[0] ?? (typeof init?.model === "string" ? init.model : null),
    stopReason: typeof result.stop_reason === "string" ? result.stop_reason : null,
    usage: resultUsage(result),
    costUsd: cost,
    costSource: cost === null ? null : "provider",
    meta: { ...meta, subtype: result.subtype ?? null, turns: result.num_turns ?? null, durationMs: result.duration_ms ?? null, modelUsage, permissionDenials: result.permission_denials ?? [] },
  };
  if (result.is_error === true) return failed(served, limited ? { kind: "rate_limited", message: "the claude CLI is rate limited" } : errorFailure(result));
  if (problem !== null) return failed(served, { kind: "not_isolated", message: problem });
  if (result.stop_reason === "refusal") return failed(served, { kind: "refused", message: "the model declined" });
  if (result.structured_output === undefined || result.structured_output === null) return failed(served, { kind: "malformed", message: "the CLI returned no structured output" }, typeof result.result === "string" ? result.result.slice(0, 4000) : null);
  return fromValue(served, request.rubric, result.structured_output, JSON.stringify(result.structured_output).slice(0, 4000));
}

export class ClaudeCodeProvider implements VisualProvider {
  readonly name = "claude-code" as const;
  private version: Promise<string | null> | null = null;

  constructor(
    private readonly spawn: Spawner = runProcess,
    private readonly env: NodeJS.ProcessEnv = process.env,
  ) {}

  private command(): string | null {
    return findClaude(this.env);
  }

  async settings(): Promise<Record<string, unknown>> {
    const command = this.command();
    this.version ??= command === null ? Promise.resolve(null) : this.spawn(command, ["--version"], { cwd: tmpdir(), env: childEnvironment(this.env), timeoutMs: 30_000, stdin: "" }).then((run) => run.stdout.trim().split("\n")[0] || null);
    return { cli: command === null ? null : basename(command), cliVersion: await this.version, timeoutMs: REQUEST_TIMEOUT_MS, maxTurns: MAX_TURNS, maxBudgetUsd: MAX_BUDGET_USD, tools: ALLOWED_TOOLS };
  }

  describeRequest(request: SampleRequest): unknown {
    return { args: claudeArgs(request), stdin: JSON.parse(claudeInput(request, (index) => `sha256:${request.images[index]!.sha256} file:${request.images[index]!.file}`)) };
  }

  async score(request: SampleRequest): Promise<SampleOutcome> {
    const command = this.command();
    if (command === null) return parseRun({ code: null, stdout: "", stderr: "", timedOut: false, missing: true }, request);
    const cwd = mkdtempSync(join(tmpdir(), "blendworks-visual-"));
    try {
      request.images.forEach((image, index) => writeFileSync(join(cwd, basename(image.file)), request.data[index]!));
      const run = await this.spawn(command, claudeArgs(request), { cwd, env: childEnvironment(this.env), timeoutMs: REQUEST_TIMEOUT_MS, stdin: claudeInput(request) });
      return parseRun(run, request);
    } finally {
      rmSync(cwd, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    }
  }
}
