import { afterEach, describe, expect, it } from "vitest";
import { BridgeConnection } from "../src/mcp/connection.js";
import { FakeBridge } from "./mcp-fake-bridge.js";
import { call, type Harness, headlessHarness, texts } from "./mcp-helpers.js";

let harness: Harness | undefined;

afterEach(async () => {
  await harness?.close();
  harness = undefined;
});

describe("requests", () => {
  it("are serialized: the bridge never sees two at once", async () => {
    harness = await headlessHarness();
    const results = await Promise.all([
      call(harness.client, "blender_slow", { ms: 60 }),
      call(harness.client, "blender_add_primitive", { type: "cube" }),
      call(harness.client, "blender_slow", { ms: 30 }),
      call(harness.client, "blender_add_primitive", { type: "plane" }),
    ]);
    expect(results.every((result) => !result.isError)).toBe(true);
    expect(harness.bridge.maxInFlight).toBe(1);
    expect(harness.bridge.requests.slice(1).map((request) => request.cmd)).toEqual(["slow", "add_primitive", "slow", "add_primitive"]);
  });

  it("time out, and the stuck session is replaced once", async () => {
    harness = await headlessHarness({ hang: new Set(["slow"]) }, { timeoutFor: (cmd) => (cmd === "slow" ? 150 : 5000) });
    const started = Date.now();
    const result = await call(harness.client, "blender_slow", { ms: 0 });
    expect(Date.now() - started).toBeLessThan(3000);
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/^timeout: slow got no reply within 0\.2 s\. Stopped the stuck session and restarted it once/);
    expect(harness.bridge.sessions).toHaveLength(2);
    const after = await call(harness.client, "blender_add_primitive", { type: "cube" });
    expect(after.isError).toBeFalsy();
  });

  it("time out against a desktop bridge without killing it", async () => {
    const bridge = new FakeBridge({ hang: new Set(["slow"]) });
    let opened = 0;
    const connection = new BridgeConnection(
      { open: async () => (opened++, bridge.link()), owned: false, label: "desktop Blender", timeoutFor: () => 100 },
      bridge.link(),
    );
    await expect(connection.request("slow", {})).rejects.toThrow(/no reply within 0\.1 s\. Desktop Blender may still be busy/);
    expect(opened).toBe(0);
    const next = await connection.request("scene_info", {});
    expect(next.notices).toEqual(["Reconnected to desktop Blender."]);
    expect(opened).toBe(1);
    await connection.close();
  });
});

describe("a crashed headless session", () => {
  it("is restarted once, and the restart is reported", async () => {
    harness = await headlessHarness({ crashOn: new Set(["slow"]) });
    await call(harness.client, "blender_add_primitive", { type: "cube" });
    const crashed = await call(harness.client, "blender_slow", { ms: 0 });
    expect(crashed.isError).toBe(true);
    expect(texts(crashed)).toMatch(/^crashed: Blender stopped while running slow \(the bridge closed the connection\)\. Restarted the session once; the scene is empty now/);
    expect(harness.bridge.sessions).toHaveLength(2);
    expect(harness.started.connection.restarts).toBe(1);
    const info = await call(harness.client, "blender_scene_info");
    expect(info.isError).toBeFalsy();
    expect(JSON.parse(texts(info))).toEqual({ objects: [] });
  });

  it("that stopped between requests is restarted before the next one, with a notice", async () => {
    harness = await headlessHarness();
    harness.bridge.sessions[0]?.close();
    await new Promise((resolve) => setTimeout(resolve, 20));
    const result = await call(harness.client, "blender_add_primitive", { type: "cube" });
    expect(result.isError).toBeFalsy();
    expect(texts(result)).toContain("The Blender session had stopped (the bridge closed the connection). Started a fresh session");
    expect(harness.bridge.sessions).toHaveLength(2);
  });

  it("is not restarted in a loop when the fresh session fails to start", async () => {
    const bridge = new FakeBridge({ crashOn: new Set(["slow"]) });
    let starts = 0;
    const connection = new BridgeConnection({
      open: async () => {
        starts += 1;
        if (starts > 1) throw new Error("blender exited with code 1");
        return bridge.link();
      },
      owned: true,
      label: "headless Blender session",
    });
    await connection.connect();
    await expect(connection.request("slow", {})).rejects.toThrow(/a fresh session failed to start: blender exited with code 1/);
    await expect(connection.request("scene_info", {})).rejects.toThrow(/a fresh session failed to start/);
    expect(starts).toBe(2);
    await connection.close();
  });
});
