import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough } from "node:stream";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it } from "vitest";
import { startHeadlessSession } from "../src/mcp/headless.js";
import { LineLink } from "../src/mcp/line-link.js";
import { BridgeError, readLine } from "../src/mcp/protocol.js";
import { killLiveSessions, type Session, SessionError, startSession } from "../src/session.js";
import { scratchDir, startWaitMs, texts, unusedPort } from "./mcp-helpers.js";
import { acquireSlot } from "../scripts/lib/slots.js";
import { blenderJobs } from "../src/blender.js";
import { beginBlendworks } from "../src/mcp/start.js";
import { useBlenderSlot, WAIT_FOR_SLOT_MS } from "./setup/slot.js";

useBlenderSlot();

const NODE = process.execPath;

function script(body: string): string[] {
  const program = `
const lines = require("node:readline").createInterface({ input: process.stdin });
const reply = (id, result) => process.stdout.write(JSON.stringify({ id, ok: true, result }) + "\\n");
lines.on("line", (line) => {
  const request = JSON.parse(line);
  if (request.id === "quit") process.exit(0);
  ${body}
});
setInterval(() => {}, 1000);
`;
  return ["-e", program];
}

const ANSWERS = script("reply(request.id, { commands: [] });");
const ANSWERS_LATE = script("setTimeout(() => reply(request.id, { commands: [] }), 400);");
const NEVER_ANSWERS = script("process.stderr.write(`pid ${process.pid}\n`);");
const EXITS_AT_ONCE = ["-e", 'process.stderr.write("Blender could not load libGL\\n"); process.exit(3);'];
const GARBLES = script('if (request.cmd === "describe") reply(request.id, {}); else process.stdout.write(\'{"id":\' + request.id + \',"ok":tr\\n\');');
const NOISY = script('process.stdout.write("Blender 5.2 banner\\n"); process.stdout.write(JSON.stringify({ id: 999, ok: true, result: {} }) + "\\n"); reply(request.id, {});');

async function callWaitingForSlot(client: Client, name: string, args: Record<string, unknown> = {}): Promise<CallToolResult> {
  return (await client.callTool({ name, arguments: args }, undefined, { timeout: WAIT_FOR_SLOT_MS })) as CallToolResult;
}

async function clientOf(server: ReturnType<typeof beginBlendworks>["server"]): Promise<Client> {
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  const client = new Client({ name: "test-client", version: "0.0.0" });
  await client.connect(clientSide);
  return client;
}

const sessions: Session[] = [];

async function open(args: string[], readyTimeoutMs?: number, onDropped?: (message: string) => void): Promise<Session> {
  const session = await startSession({
    blender: NODE,
    args,
    workspace: mkdtempSync(join(tmpdir(), "blendworks-ready-")),
    ...(readyTimeoutMs === undefined ? {} : { readyTimeoutMs }),
    ...(onDropped === undefined ? {} : { onDropped }),
  });
  sessions.push(session);
  return session;
}

afterEach(async () => {
  await Promise.all(sessions.splice(0).map((session) => session.kill()));
});

describe("the ready handshake", () => {
  it("resolves only after the bridge answered describe, even when it is slow", async () => {
    const started = performance.now();
    await open(ANSWERS_LATE, 5000);
    expect(performance.now() - started).toBeGreaterThanOrEqual(380);
  });

  it("fails with the exit code and the last output when Blender exits early", async () => {
    await expect(open(EXITS_AT_ONCE, 5000)).rejects.toThrow(/never became ready: Blender exited \(code 3.*Blender could not load libGL/s);
  });

  it("kills a Blender that never answers, and says how long it waited", async () => {
    const seen: string[] = [];
    await expect(startSession({ blender: NODE, args: NEVER_ANSWERS, workspace: scratchDir(), readyTimeoutMs: 300, onStderr: (line) => seen.push(line) })).rejects.toThrow(/did not answer within 0\.3 s/);
    const pid = Number(/pid (\d+)/.exec(seen.join(" "))?.[1]);
    expect(pid).toBeGreaterThan(0);
    expect(() => process.kill(pid, 0)).toThrow();
  });

  it("fails a headless start with a SessionError that names the cause", async () => {
    const error = await startHeadlessSession({ workspace: scratchDir(), allowPython: false }, () => undefined, { blender: NODE, args: EXITS_AT_ONCE, readyTimeoutMs: 3000 }).catch((failure: unknown) => failure);
    expect(error).toBeInstanceOf(SessionError);
    expect((error as SessionError).message).toMatch(/Blender exited \(code 3/);
  });
});

describe("one reply parser", () => {
  it("reads a garbled line for a pending id as a protocol error in both the session and the line link", async () => {
    const session = await open(GARBLES, 3000);
    const failure = await session.call("scene_info", {}, { timeoutMs: 20_000 }).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(SessionError);
    expect((failure as SessionError).kind).toBe("protocol");

    const input = new PassThrough();
    const output = new PassThrough();
    const link = new LineLink(input, output, () => undefined);
    const pending = link.call("scene_info", {});
    input.write('{"id":1,"ok":tr\n');
    const error = await pending.catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(BridgeError);
    expect((error as BridgeError).code).toBe("protocol");
  });

  it("reports a garbled line that belongs to nobody, and one for a request nobody waits for, instead of dropping it silently", async () => {
    const dropped: string[] = [];
    const input = new PassThrough();
    const link = new LineLink(input, new PassThrough(), () => undefined, (message) => dropped.push(message));
    input.write("not json at all\n");
    input.write('{"id":42,"ok":true,"result":{}}\n');
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(dropped).toHaveLength(2);
    expect(dropped[0]).toMatch(/dropped an unreadable bridge line/);
    expect(dropped[1]).toMatch(/dropped a bridge reply for request 42/);
    await link.close();
    const noisy: string[] = [];
    const session = await open(NOISY, 3000, (message) => noisy.push(message));
    await session.call("scene_info", {});
    expect(noisy.some((message) => /request 999/.test(message))).toBe(true);
    expect(noisy.some((message) => /unreadable/.test(message))).toBe(true);
  });

  it("is one function: the same lines give the same verdicts", () => {
    expect(readLine('{"id":7,"ok":true,"result":{"a":1}}')).toMatchObject({ kind: "reply", reply: { id: 7, ok: true } });
    expect(readLine('{"id":7,"ok":tr')).toMatchObject({ kind: "garbled", id: 7 });
    expect(readLine("Blender 5.2")).toMatchObject({ kind: "garbled", id: undefined });
    expect(readLine("  ")).toEqual({ kind: "ignored" });
  });
});

describe("early exits through the server", () => {
  it("do not respawn Blender on every call, and a later call tries again", async () => {
    let clock = 10_000;
    let spawns = 0;
    const begun = beginBlendworks({
      workspace: scratchDir(),
      port: await unusedPort(),
      allowPython: false,
      listWaitMs: 20,
      bootBackoffMs: [1000],
      startWaitMs: startWaitMs(20_000),
      connection: { now: () => clock, restartDelaysMs: [] },
      startHeadless: (options) => {
        spawns += 1;
        return startHeadlessSession(options, () => undefined, { blender: NODE, args: spawns === 1 ? EXITS_AT_ONCE : ANSWERS_LATE, readyTimeoutMs: 3000 });
      },
    });
    const client = await clientOf(begun.server);
    try {
      const first = await callWaitingForSlot(client, "blender_scene_info");
      expect(first.isError).toBe(true);
      expect(texts(first)).toMatch(/Blender exited \(code 3.*libGL.*Check that BLENDER points to a working Blender.*Set BLENDER/s);
      const second = await callWaitingForSlot(client, "blender_scene_info");
      expect(texts(second)).toMatch(/tries to start Blender again in 1 s/);
      expect(spawns).toBe(1);
      clock += 1500;
      const third = await callWaitingForSlot(client, "blender_find_tools", { query: "scene" });
      expect(spawns).toBe(2);
      expect(texts(third)).not.toMatch(/Blender exited/);
    } finally {
      await client.close();
      await begun.stop();
    }
  });

  it("count only the start itself against the server's start wait, not the queue for a Blender slot", async () => {
    const held = await Promise.all(Array.from({ length: blenderJobs() }, () => acquireSlot({ label: "session-ready: every slot busy" })));
    const release = setTimeout(() => held.forEach((slot) => slot.release()), 3000);
    const begun = beginBlendworks({
      workspace: scratchDir(),
      port: await unusedPort(),
      allowPython: false,
      listWaitMs: 20,
      startWaitMs: startWaitMs(1000),
      startHeadless: (options) => startHeadlessSession(options, () => undefined, { blender: NODE, args: ANSWERS, readyTimeoutMs: 3000 }),
    });
    const client = await clientOf(begun.server);
    try {
      const result = await callWaitingForSlot(client, "blender_find_tools", { query: "scene" });
      expect(texts(result)).not.toMatch(/still starting/);
      expect(result.isError ?? false).toBe(false);
    } finally {
      clearTimeout(release);
      held.forEach((slot) => slot.release());
      await client.close();
      await begun.stop();
    }
  });
});

describe("process exit", () => {
  it("killLiveSessions stops every Blender child that is still running", async () => {
    const session = await open(ANSWERS, 3000);
    const alive = () => {
      try {
        process.kill(session.pid!, 0);
        return true;
      } catch {
        return false;
      }
    };
    expect(alive()).toBe(true);
    killLiveSessions();
    await session.exited;
    expect(alive()).toBe(false);
  });
});
