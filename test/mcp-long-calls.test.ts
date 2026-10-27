import type { Progress as McpProgress } from "@modelcontextprotocol/sdk/types.js";
import { afterEach, describe, expect, it } from "vitest";
import { BridgeConnection } from "../src/mcp/connection.js";
import type { BridgeLink } from "../src/mcp/protocol.js";
import { FakeBridge } from "./mcp-fake-bridge.js";
import { call, type Harness, headlessHarness, texts } from "./mcp-helpers.js";

let harness: Harness | undefined;

afterEach(async () => {
  await harness?.close();
  harness = undefined;
});

function waitFor(check: () => boolean, limitMs = 3000): Promise<void> {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const poll = setInterval(() => {
      if (check()) {
        clearInterval(poll);
        resolve();
      } else if (Date.now() - started > limitMs) {
        clearInterval(poll);
        reject(new Error("the condition did not hold in time"));
      }
    }, 5);
  });
}

describe("progress notifications", () => {
  it("arrive while a call runs and while one waits in the queue", async () => {
    harness = await headlessHarness({}, { progressIntervalMs: 40 });
    const first: McpProgress[] = [];
    const second: McpProgress[] = [];
    const running = harness.client.callTool({ name: "blender_slow", arguments: { ms: 400 } }, undefined, { onprogress: (progress) => first.push(progress) });
    const queued = harness.client.callTool({ name: "blender_add_primitive", arguments: { type: "cube" } }, undefined, { onprogress: (progress) => second.push(progress) });
    await Promise.all([running, queued]);
    expect(first.length).toBeGreaterThanOrEqual(3);
    expect(first.at(-1)?.message).toMatch(/^slow running for \d+ s; it stops after 120 s of running$/);
    expect(first.map((progress) => progress.progress)).toEqual([...first.map((progress) => progress.progress)].sort((a, b) => a - b));
    expect(second[0]?.message).toMatch(/^add_primitive waiting behind 1 earlier request for \d+ s/);
  });

  it("are not sent without a progress token", async () => {
    harness = await headlessHarness({}, { progressIntervalMs: 20 });
    const seen: string[] = [];
    harness.client.fallbackNotificationHandler = async (notification) => {
      seen.push(notification.method);
    };
    await call(harness.client, "blender_slow", { ms: 150 });
    expect(seen).not.toContain("notifications/progress");
  });
});

describe("cancellation", () => {
  it("stops a running call by restarting the session, which reloads the autosave", async () => {
    harness = await headlessHarness({ hang: new Set(["slow"]) }, { progressIntervalMs: 30 });
    await call(harness.client, "blender_add_primitive", { type: "cube" });
    const controller = new AbortController();
    let progressed = 0;
    const cancelled = harness.client.callTool({ name: "blender_slow", arguments: { ms: 0 } }, undefined, {
      signal: controller.signal,
      onprogress: () => {
        progressed += 1;
        if (progressed === 1) controller.abort();
      },
    });
    await expect(cancelled).rejects.toThrow(/abort/i);
    const bridge = harness.bridge;
    await waitFor(() => bridge.requests.at(-1)?.cmd === "recover");
    expect(bridge.sessions).toHaveLength(2);
    const info = await call(harness.client, "blender_scene_info");
    expect(JSON.parse(texts(info))).toEqual({ objects: [{ name: "cube.0" }] });
  });

  it("drops a queued call before it reaches Blender", async () => {
    harness = await headlessHarness();
    const controller = new AbortController();
    const running = call(harness.client, "blender_slow", { ms: 200 });
    const queued = harness.client.callTool({ name: "blender_add_primitive", arguments: { type: "torus" } }, undefined, { signal: controller.signal });
    await new Promise((resolve) => setTimeout(resolve, 30));
    controller.abort();
    await expect(queued).rejects.toThrow(/abort/i);
    expect((await running).isError).toBeFalsy();
    await call(harness.client, "blender_scene_info");
    expect(harness.bridge.requests.some((request) => request.args["type"] === "torus")).toBe(false);
    expect(harness.bridge.sessions).toHaveLength(1);
  });
});

describe("per-call timeouts", () => {
  it("accept timeout_seconds up to the command's cap and refuse more", async () => {
    harness = await headlessHarness({ hang: new Set(["slow"]) });
    const started = Date.now();
    const stopped = await call(harness.client, "blender_slow", { ms: 0, timeout_seconds: 0.2 });
    expect(Date.now() - started).toBeLessThan(3000);
    expect(texts(stopped)).toMatch(/^timeout: slow got no reply within 0\.2 s\. Stopped the session\. Restarted it\./);
    const refused = await call(harness.client, "blender_add_primitive", { type: "cube", timeout_seconds: 601 });
    expect(refused.isError).toBe(true);
    expect(texts(refused)).toBe("bad_args: timeout_seconds must be a number of seconds above 0 and at most 600 for add_primitive");
    expect(harness.bridge.requests.at(-1)?.cmd).not.toBe("add_primitive");
    const sent = await call(harness.client, "blender_add_primitive", { type: "cube", timeout_seconds: 30 });
    expect(sent.isError).toBeFalsy();
    expect(harness.bridge.requests.at(-1)?.args).toEqual({ type: "cube" });
  });
});

describe("close", () => {
  it("never hangs, even with a call running, calls queued and a link that will not close", async () => {
    const bridge = new FakeBridge({ hang: new Set(["slow"]) });
    const inner = bridge.link();
    const stubborn: BridgeLink = {
      call: (cmd, args) => inner.call(cmd, args),
      close: () => new Promise<void>(() => undefined),
      kill: () => new Promise<void>(() => undefined),
      onClose: (listener) => inner.onClose(listener),
    };
    const connection = new BridgeConnection({ open: async () => stubborn, owned: true, label: "headless Blender session", closeLimitMs: 150 }, stubborn);
    const running = connection.request("slow", {}).catch((error: unknown) => error);
    const queued = connection.request("scene_info", {}).catch((error: unknown) => error);
    await new Promise((resolve) => setTimeout(resolve, 20));
    const started = Date.now();
    await connection.close();
    expect(Date.now() - started).toBeLessThan(1000);
    expect(String(await running)).toMatch(/stopped because the connection was closed/);
    expect(String(await queued)).toMatch(/closed before the request ran/);
    await expect(connection.request("scene_info", {})).rejects.toThrow(/the connection was closed/);
  });
});
