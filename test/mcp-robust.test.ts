import { join } from "node:path";
import { EventEmitter } from "node:events";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { ToolListChangedNotificationSchema } from "@modelcontextprotocol/sdk/types.js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { badArguments, SCHEMA_ECHO_CHARS } from "../src/mcp/errors.js";
import { BridgeConnection } from "../src/mcp/connection.js";
import { installProcessGuards } from "../src/mcp/hygiene.js";
import { createBootedServer } from "../src/mcp/server.js";
import { beginBlendworks } from "../src/mcp/start.js";
import { FakeBridge } from "./mcp-fake-bridge.js";
import { call, headlessHarness, type Harness, scratchDir, texts, unusedPort } from "./mcp-helpers.js";
import { libraryHarness } from "./library-helpers.js";

let harness: Harness | undefined;
const closers: (() => Promise<void>)[] = [];

afterEach(async () => {
  await harness?.close();
  harness = undefined;
  for (const close of closers.splice(0).reverse()) await close();
});

function gate(): { open: () => void; opened: Promise<void> } {
  let open: () => void = () => undefined;
  const opened = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { open, opened };
}

async function clientFor(server: ReturnType<typeof createBootedServer>["server"]): Promise<Client> {
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  const client = new Client({ name: "test-client", version: "0.0.0" });
  await client.connect(clientSide);
  closers.push(() => client.close());
  return client;
}

describe("restarting a session", () => {
  it("retries a failing first open with backoff and the session survives", async () => {
    const bridge = new FakeBridge({ crashOn: new Set(["slow"]) });
    const sleeps: number[] = [];
    let opens = 0;
    const connection = new BridgeConnection({
      open: async () => {
        opens += 1;
        if (opens === 2 || opens === 3) throw new Error("blender.exe is locked");
        return bridge.link();
      },
      owned: true,
      label: "headless Blender session",
      restartDelaysMs: [10, 20],
      sleep: async (ms) => void sleeps.push(ms),
    });
    await connection.connect();
    const crashed = await connection.request("slow", {}).catch((error: unknown) => error as Error);
    expect(String(crashed)).toMatch(/Started a fresh session/);
    expect(opens).toBe(4);
    expect(sleeps).toEqual([10, 20]);
    expect((await connection.request("scene_info", {})).result).toEqual({ objects: [] });
    await connection.close();
  });

  it("is dead only after repeated failures in a window, names BLENDER, and tries again after the cooldown", async () => {
    const bridge = new FakeBridge({ crashOn: new Set(["slow"]) });
    let clock = 1_000_000;
    let opens = 0;
    let locked = false;
    const connection = new BridgeConnection({
      open: async () => {
        opens += 1;
        if (locked) throw new Error("blender.exe is locked");
        return bridge.link();
      },
      owned: true,
      label: "headless Blender session",
      restartDelaysMs: [],
      deadAfterFailures: 2,
      deadCooldownMs: 60_000,
      now: () => clock,
    });
    await connection.connect();
    locked = true;
    await expect(connection.request("slow", {})).rejects.toThrow(/failed to start after 1 attempt: blender\.exe is locked\. Check that BLENDER points to a working Blender.*the next call tries again/);
    const opensBeforeDead = opens;
    await expect(connection.request("scene_info", {})).rejects.toThrow(/2 restarts have failed within .*BLENDER.*will not try again for 60 s.*restart the MCP server/);
    const opensWhenDead = opens;
    expect(opensWhenDead).toBe(opensBeforeDead + 1);
    await expect(connection.request("scene_info", {})).rejects.toThrow(/will not try again for 60 s/);
    expect(opens).toBe(opensWhenDead);
    clock += 61_000;
    locked = false;
    expect((await connection.request("scene_info", {})).result).toEqual({ objects: [] });
    await connection.close();
  });
});

describe("a garbled reply for a pending request", () => {
  it("fails that call at once with a protocol error and replaces the session", async () => {
    harness = await headlessHarness({ garble: new Set(["slow"]) }, { timeoutFor: () => 20_000 });
    const result = await call(harness.client, "blender_slow", { ms: 0 });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/^protocol: slow got a reply that could not be read \(bridge sent a line that is not JSON: \{"id":\d+,"ok":tr\)\. Stopped the session\. Restarted it\./);
    expect(harness.bridge.sessions).toHaveLength(2);
    expect((await call(harness.client, "blender_add_primitive", { type: "cube" })).isError).toBeFalsy();
  });
});

describe("a slow Blender start", () => {
  async function begin(extra: Partial<Parameters<typeof beginBlendworks>[0]> = {}) {
    const bridge = new FakeBridge();
    const release = gate();
    const logs: string[] = [];
    let starts = 0;
    const begun = beginBlendworks({
      workspace: join(scratchDir(), "workspace"),
      port: await unusedPort(),
      allowPython: false,
      listWaitMs: 40,
      log: (line) => logs.push(line),
      startHeadless: async () => {
        starts += 1;
        await release.opened;
        return bridge.link();
      },
      ...extra,
    });
    closers.push(() => begun.stop());
    return { begun, bridge, release, logs, starts: () => starts };
  }

  it("answers initialize before Blender is ready, makes a call wait for it, and then lists the tools", async () => {
    const { begun, release, starts } = await begin();
    const client = await clientFor(begun.server);
    expect(client.getInstructions()).toContain("blender_");
    await vi.waitFor(() => expect(starts()).toBe(1));
    let changed = 0;
    client.setNotificationHandler(ToolListChangedNotificationSchema, () => {
      changed += 1;
    });
    const early = (await client.listTools()).tools.map((tool) => tool.name);
    expect(early).toContain("blender_find_tools");
    expect(early).not.toContain("blender_add_primitive");
    const waiting = call(client, "blender_add_primitive", { type: "cube" });
    await new Promise((resolve) => setTimeout(resolve, 100));
    release.open();
    expect(JSON.parse(texts(await waiting))).toEqual({ object: "cube.0" });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(changed).toBeGreaterThan(0);
    expect((await client.listTools()).tools.map((tool) => tool.name)).toContain("blender_add_primitive");
  });

  it("makes a call that cannot wait long enough say that Blender is still starting", async () => {
    const { begun, release } = await begin();
    const client = await clientFor(begun.server);
    const result = await call(client, "blender_add_primitive", { type: "cube", timeout_seconds: 0.2 });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/^timeout: Blender is still starting after 0\.2 s; it keeps starting in the background.*timeout_seconds/);
    release.open();
    expect((await call(client, "blender_add_primitive", { type: "cube" })).isError).toBeFalsy();
  });
});

describe("a Blender that cannot start", () => {
  it("becomes a tool error with the cause and the fix, backs off, and starts on a later call", async () => {
    const bridge = new FakeBridge();
    let clock = 5_000;
    let starts = 0;
    const begun = beginBlendworks({
      workspace: join(scratchDir(), "workspace"),
      port: await unusedPort(),
      allowPython: false,
      listWaitMs: 40,
      bootBackoffMs: [1000],
      connection: { now: () => clock, restartDelaysMs: [] },
      startHeadless: async () => {
        starts += 1;
        if (starts === 1) throw new Error("spawn blender ENOENT");
        return bridge.link();
      },
    });
    closers.push(() => begun.stop());
    const client = await clientFor(begun.server);
    const first = await call(client, "blender_add_primitive", { type: "cube" });
    expect(first.isError).toBe(true);
    expect(texts(first)).toMatch(/^disconnected: cannot start headless Blender session: spawn blender ENOENT\. Check that BLENDER points to a working Blender.*Set BLENDER to the full path.*restart the MCP server/);
    const again = await call(client, "blender_add_primitive", { type: "cube" });
    expect(texts(again)).toMatch(/spawn blender ENOENT.*tries to start Blender again in 1 s/);
    expect(starts).toBe(1);
    clock += 1500;
    expect(JSON.parse(texts(await call(client, "blender_add_primitive", { type: "cube" })))).toEqual({ object: "cube.0" });
    expect(starts).toBe(2);
  });

  it("still searches and downloads from the library, which needs no Blender", async () => {
    const lib = libraryHarness();
    const booted = createBootedServer({
      workspace: lib.workspace,
      library: lib.library,
      toolsets: { kind: "all" },
      listWaitMs: 40,
      starter: () => Promise.reject(new Error("spawn blender ENOENT")),
    });
    const client = await clientFor(booted.server);
    const found = await call(client, "library_search", { query: "barrel" });
    expect(found.isError, texts(found)).toBeFalsy();
    expect(JSON.parse(texts(found)).results.map((entry: { id: string }) => entry.id)).toContain("Barrel_01");
    const blender = await call(client, "blender_scene_info");
    expect(texts(blender)).toContain("spawn blender ENOENT");
  });
});

describe("choosing desktop or headless", () => {
  it("logs which mode it chose and why", async () => {
    const logs: string[] = [];
    const nothing = beginBlendworks({ workspace: scratchDir(), port: await unusedPort(), allowPython: false, log: (line) => logs.push(line), startHeadless: async () => new FakeBridge().link() });
    closers.push(() => nothing.stop());
    await nothing.ready;
    expect(logs.join("\n")).toMatch(/no desktop Blender: nothing answered on 127\.0\.0\.1:\d+ \(.*\); started a headless session/);

    const desktop = new FakeBridge();
    const { port, server } = await desktop.listen();
    closers.push(() => new Promise((resolve) => server.close(() => resolve())));
    const logsDesktop: string[] = [];
    const chosen = beginBlendworks({ workspace: scratchDir(), port, allowPython: false, log: (line) => logsDesktop.push(line), startHeadless: async () => new FakeBridge().link() });
    closers.push(() => chosen.stop());
    expect((await chosen.ready).mode).toBe("desktop");
    expect(logsDesktop.join("\n")).toMatch(/using desktop Blender on 127\.0\.0\.1:\d+ with \d+ commands \(it answered describe within 1000 ms\)/);
  });

  it("waits again when the port is open but slow, and keeps the desktop Blender", async () => {
    const slow = new FakeBridge({ delayMs: 400 });
    const { port, server } = await slow.listen();
    closers.push(() => new Promise((resolve) => server.close(() => resolve())));
    const logs: string[] = [];
    let headless = 0;
    const chosen = beginBlendworks({
      workspace: scratchDir(),
      port,
      allowPython: false,
      desktopAnswerMs: 150,
      desktopSlowAnswerMs: 3000,
      log: (line) => logs.push(line),
      startHeadless: async () => {
        headless += 1;
        return new FakeBridge().link();
      },
    });
    closers.push(() => chosen.stop());
    expect((await chosen.ready).mode).toBe("desktop");
    expect(headless).toBe(0);
    expect(logs.join("\n")).toMatch(/the port was open but slow: it answered describe after \d+ ms, on the second try/);
  });

  it("falls back to headless and says that a busy desktop Blender is probably listening", async () => {
    const hung = new FakeBridge({ hang: new Set(["describe"]) });
    const { port, server } = await hung.listen();
    closers.push(() => new Promise((resolve) => server.close(() => resolve())));
    const logs: string[] = [];
    const chosen = beginBlendworks({ workspace: scratchDir(), port, allowPython: false, desktopAnswerMs: 100, desktopSlowAnswerMs: 300, log: (line) => logs.push(line), startHeadless: async () => new FakeBridge().link() });
    closers.push(() => chosen.stop());
    expect((await chosen.ready).mode).toBe("headless");
    expect(logs.join("\n")).toMatch(/is open but gave no describe answer within 300 ms \(tried twice, 100 ms then 200 ms more\); a busy desktop Blender is probably listening there/);
  });
});

describe("process hygiene", () => {
  it("shuts down once on an unhandled rejection or an uncaught exception, and kills its children on exit", () => {
    const target = new EventEmitter();
    const shutdowns: number[] = [];
    const logs: string[] = [];
    let killed = 0;
    installProcessGuards(target, {
      shutdown: async (code) => void shutdowns.push(code),
      killChildren: () => void (killed += 1),
      log: (line) => logs.push(line),
    });
    target.emit("unhandledRejection", new Error("boom"));
    target.emit("uncaughtException", new Error("second"));
    expect(shutdowns).toEqual([1]);
    expect(logs[0]).toMatch(/unhandled rejection: Error: boom/);
    target.emit("exit", 0);
    expect(killed).toBe(1);
  });
});

describe("error texts", () => {
  it("a timeout says to pass timeout_seconds and the maximum for that command", async () => {
    harness = await headlessHarness({ hang: new Set(["slow"]) }, { timeoutFor: (cmd) => (cmd === "slow" ? 100 : 5000) });
    const result = await call(harness.client, "blender_slow", { ms: 0 });
    expect(texts(result)).toMatch(/ To wait longer, pass timeout_seconds \(at most 600 s for slow\)\.$/);
  });

  it("bad_args lists the failing fields first and caps the schema echo", async () => {
    harness = await headlessHarness({ wide: true });
    const result = await call(harness.client, "blender_wide_schema", { setting_3: 5, setting_9: true });
    expect(result.isError).toBe(true);
    const text = texts(result);
    expect(text).toMatch(/^bad_args: blender_wide_schema refused these arguments: setting_3: .*; setting_9: .*\. Its schema: \{/);
    expect(text).toContain("[cut: the schema has");
    expect(text.length).toBeLessThan(SCHEMA_ECHO_CHARS + 700);
  });

  it("bad_args shows a short schema whole", () => {
    expect(badArguments("blender_x", ["size: Too small"], { type: "object" })).toBe('bad_args: blender_x refused these arguments: size: Too small. Its schema: {"type":"object"}');
  });
});
