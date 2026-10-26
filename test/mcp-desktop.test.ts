import { createServer } from "node:net";
import type { AddressInfo, Server } from "node:net";
import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_PORT, desktopPort } from "../src/mcp/desktop.js";
import { type Started, startBlendworks } from "../src/mcp/start.js";
import { FakeBridge } from "./mcp-fake-bridge.js";
import { call, connectClient, scratchDir, texts, unusedPort } from "./mcp-helpers.js";

const servers: Server[] = [];
const started: Started[] = [];

afterEach(async () => {
  for (const one of started.splice(0)) await one.connection.close();
  for (const server of servers.splice(0)) await new Promise((resolve) => server.close(resolve));
});

function headlessStub(bridge: FakeBridge, counter: { starts: number }) {
  return async () => {
    counter.starts += 1;
    return bridge.link();
  };
}

describe("BLENDWORKS_PORT", () => {
  it("defaults to 9876", () => {
    expect(DEFAULT_PORT).toBe(9876);
    expect(desktopPort({})).toBe(9876);
    expect(desktopPort({ BLENDWORKS_PORT: "" })).toBe(9876);
  });

  it("is read from the environment and checked", () => {
    expect(desktopPort({ BLENDWORKS_PORT: "12345" })).toBe(12345);
    expect(() => desktopPort({ BLENDWORKS_PORT: "70000" })).toThrow(/BLENDWORKS_PORT/);
    expect(() => desktopPort({ BLENDWORKS_PORT: "abc" })).toThrow(/BLENDWORKS_PORT/);
  });
});

describe("choosing the bridge", () => {
  it("uses a desktop add-on that answers describe within 1 s", async () => {
    const desktop = new FakeBridge();
    const { port, server } = await desktop.listen();
    servers.push(server);
    const counter = { starts: 0 };
    const one = await startBlendworks({ workspace: scratchDir(), port, allowPython: false, startHeadless: headlessStub(new FakeBridge(), counter) });
    started.push(one);
    expect(one.mode).toBe("desktop");
    expect(counter.starts).toBe(0);
    const client = await connectClient(one);
    const result = await call(client, "blender_add_primitive", { type: "cube" });
    expect(JSON.parse(texts(result))).toEqual({ object: "cube.0" });
    expect(desktop.requests.map((request) => request.cmd)).toEqual(["describe", "add_primitive"]);
    await client.close();
  });

  it("starts its own headless session when nothing listens", async () => {
    const counter = { starts: 0 };
    const one = await startBlendworks({ workspace: scratchDir(), port: await unusedPort(), allowPython: false, startHeadless: headlessStub(new FakeBridge(), counter) });
    started.push(one);
    expect(one.mode).toBe("headless");
    expect(counter.starts).toBe(1);
  });

  it("starts its own headless session when the port does not answer describe within 1 s", async () => {
    const silent = createServer((socket) => socket.resume());
    await new Promise<void>((resolve) => silent.listen(0, "127.0.0.1", resolve));
    servers.push(silent);
    const counter = { starts: 0 };
    const before = Date.now();
    const one = await startBlendworks({
      workspace: scratchDir(),
      port: (silent.address() as AddressInfo).port,
      allowPython: false,
      startHeadless: headlessStub(new FakeBridge(), counter),
    });
    started.push(one);
    const waited = Date.now() - before;
    expect(one.mode).toBe("headless");
    expect(counter.starts).toBe(1);
    expect(waited).toBeGreaterThanOrEqual(950);
    expect(waited).toBeLessThan(3000);
  });

  it("starts its own headless session when the add-on answers too late", async () => {
    const slowDesktop = new FakeBridge({ delayMs: 1500 });
    const { port, server } = await slowDesktop.listen();
    servers.push(server);
    const counter = { starts: 0 };
    const one = await startBlendworks({ workspace: scratchDir(), port, allowPython: false, startHeadless: headlessStub(new FakeBridge(), counter) });
    started.push(one);
    expect(one.mode).toBe("headless");
  });
});
