import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { childEnvironment, claudeArgs, claudeInput, ClaudeCodeProvider, MAX_TURNS } from "../../src/judge/visual/claude-code.js";
import { findClaude } from "../../src/judge/visual/process.js";
import { EVIDENCE_INTRO, SYSTEM_PROMPT, trustedBlock } from "../../src/judge/visual/prompt.js";
import { freshDir } from "./helpers.js";
import { answer, BRIEF, CLI_INIT, cliOutput, cliResult, fakeSpawn, RUBRIC, sampleRequest } from "./visual-helpers.js";

function cliEnv(dir: string): NodeJS.ProcessEnv {
  const binary = join(dir, "claude.exe");
  writeFileSync(binary, "");
  return { BLENDWORKS_CLAUDE: binary, PATH: "", CLAUDECODE: "1", CLAUDE_CODE_MESSAGING_SOCKET: "pipe", CLAUDE_CONFIG_DIR: "C:/config", HOME: "C:/home" };
}

describe("the claude-code provider", () => {
  it("runs the CLI isolated: no tools, no settings, hooks, CLAUDE.md, MCP or slash commands, no session, capped turns", () => {
    const request = sampleRequest(freshDir("visual-cli", "args"));
    expect(claudeArgs(request)).toEqual([
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
      "2",
      "--model",
      "claude-opus-5-5",
      "--effort",
      "high",
      "--system-prompt",
      `${SYSTEM_PROMPT}\n\n${trustedBlock(BRIEF, RUBRIC)}`,
      "--json-schema",
      JSON.stringify(request.schema),
    ]);
  });

  it("sends the captions and images as one user message after the trusted system prompt", () => {
    const request = sampleRequest(freshDir("visual-cli", "input"));
    const message = JSON.parse(claudeInput(request));
    expect(message).toEqual({
      type: "user",
      message: {
        role: "user",
        content: [
          { type: "text", text: EVIDENCE_INTRO },
          { type: "text", text: "Image 1 of 2: the front view, rendered by the judge." },
          { type: "image", source: { type: "base64", media_type: "image/png", data: request.data[0]!.toString("base64") } },
          { type: "text", text: "Image 2 of 2: the hero close-up, rendered by the judge." },
          { type: "image", source: { type: "base64", media_type: "image/png", data: request.data[1]!.toString("base64") } },
        ],
      },
    });
    expect(claudeInput(request)).not.toContain(BRIEF);
  });

  it("drops the parent session's CLAUDE variables but keeps the config folder that holds the login", () => {
    expect(childEnvironment({ CLAUDECODE: "1", CLAUDE_CODE_MESSAGING_SOCKET: "x", CLAUDE_PID: "1", CLAUDE_CONFIG_DIR: "C:/c", PATH: "p", ANTHROPIC_BASE_URL: "u" })).toEqual({ CLAUDE_CONFIG_DIR: "C:/c", PATH: "p", ANTHROPIC_BASE_URL: "u" });
  });

  it("returns the validated structured output with the CLI's usage, cost and version, from a folder of only the renders", async () => {
    const dir = freshDir("visual-cli", "ok");
    let seen: string[] = [];
    let cwd = "";
    const spawn = fakeSpawn((args, call) => {
      if (args[0] === "--version") return { stdout: "2.1.311 (Claude Code)\n" };
      cwd = spawn.calls[call]!.options.cwd;
      seen = readdirSync(cwd).sort();
      return { stdout: cliOutput([CLI_INIT, cliResult({ structured_output: answer([0.9, 0.7]) })]) };
    });
    const env = cliEnv(dir);
    const provider = new ClaudeCodeProvider(spawn, env);
    const outcome = await provider.score(sampleRequest(dir));
    expect(seen).toEqual(["closeup-hero.png", "view-front.png"]);
    expect(existsSync(cwd)).toBe(false);
    expect(spawn.calls[0]!.options.env).toEqual({ BLENDWORKS_CLAUDE: env.BLENDWORKS_CLAUDE, PATH: "", CLAUDE_CONFIG_DIR: "C:/config", HOME: "C:/home" });
    expect(spawn.calls[0]!.options.timeoutMs).toBe(300_000);
    expect(outcome).toMatchObject({ status: "ok", answer: answer([0.9, 0.7]), servedBy: "claude-opus-5-5", costUsd: 0.26, costSource: "provider", meta: { cli: { version: "2.1.311", tools: ["StructuredOutput"] }, turns: 2 } });
    expect(outcome.usage).toEqual({ inputTokens: 2, outputTokens: 57, cacheCreationInputTokens: 4287, cacheReadInputTokens: 0 });
    expect(await provider.settings()).toMatchObject({ cli: "claude.exe", cliVersion: "2.1.311 (Claude Code)", maxTurns: MAX_TURNS, tools: ["StructuredOutput"] });
  });

  it("gives the documented failure for every way the CLI can fail", async () => {
    const dir = freshDir("visual-cli", "failures");
    const env = cliEnv(dir);
    const request = sampleRequest(dir);
    const cases: [Parameters<typeof fakeSpawn>[0] extends (...args: never[]) => infer R ? R : never, string, string][] = [
      [{ stdout: cliOutput([CLI_INIT, cliResult({ is_error: true, result: "Not logged in · Please run /login" })]) }, "error", "not_logged_in"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ is_error: true, api_error_status: 401, result: "Invalid bearer token" })]) }, "error", "not_logged_in"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ is_error: true, api_error_status: 429, result: "rate limited" })]) }, "error", "rate_limited"],
      [{ stdout: cliOutput([CLI_INIT, { type: "rate_limit_event", rate_limit_info: { status: "rejected" } }]), code: 1 }, "error", "rate_limited"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ is_error: true, subtype: "error_during_execution", result: "boom" })]) }, "error", "api_error"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ is_error: true, subtype: "error_max_turns" })]) }, "malformed", "malformed"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ stop_reason: "refusal", structured_output: null })]) }, "refused", "refused"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ structured_output: { ...answer([2, 0.5]) } })]) }, "malformed", "malformed"],
      [{ stdout: cliOutput([CLI_INIT, cliResult({ result: "plain text" })]) }, "malformed", "malformed"],
      [{ stdout: cliOutput([{ ...CLI_INIT, tools: ["StructuredOutput", "Read", "Bash"] }, cliResult({ structured_output: answer([1, 1]) })]) }, "error", "not_isolated"],
      [{ stdout: cliOutput([{ ...CLI_INIT, mcp_servers: [{ name: "solive" }] }, cliResult({ structured_output: answer([1, 1]) })]) }, "error", "not_isolated"],
      [{ stdout: cliOutput([cliResult({ structured_output: answer([1, 1]) })]) }, "error", "not_isolated"],
      [{ timedOut: true, code: null }, "error", "timeout"],
      [{ missing: true, code: null }, "error", "unavailable"],
      [{ code: 1, stderr: "panic\n" }, "error", "api_error"],
    ];
    for (const [run, status, kind] of cases) {
      const outcome = await new ClaudeCodeProvider(fakeSpawn(() => run), env).score(request);
      expect({ status: outcome.status, kind: outcome.failure?.kind }).toEqual({ status, kind });
      expect(outcome.answer).toBeNull();
    }
    const missing = await new ClaudeCodeProvider(fakeSpawn(() => ({})), { PATH: "" }).score(request);
    expect(missing.failure).toEqual({ kind: "unavailable", message: "the claude CLI is not installed or not on PATH" });
  });

  it("finds the CLI by BLENDWORKS_CLAUDE, then on PATH, through the npm shim on Windows", () => {
    const dir = freshDir("visual-cli", "find");
    const bin = join(dir, "node_modules", "@anthropic-ai", "claude-code", "bin");
    mkdirSync(bin, { recursive: true });
    writeFileSync(join(bin, "claude.exe"), "");
    writeFileSync(join(dir, "claude.cmd"), "");
    writeFileSync(join(dir, "claude"), "");
    expect(findClaude({ PATH: dir }, "win32")).toBe(join(bin, "claude.exe"));
    expect(findClaude({ PATH: dir }, "linux")).toBe(join(dir, "claude"));
    expect(findClaude({ BLENDWORKS_CLAUDE: join(dir, "claude"), PATH: "" }, "linux")).toBe(join(dir, "claude"));
    expect(findClaude({ BLENDWORKS_CLAUDE: join(dir, "absent"), PATH: dir }, "linux")).toBeNull();
    expect(findClaude({ PATH: "" }, "win32")).toBeNull();
  });
});
