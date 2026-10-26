import { mkdtempSync } from "node:fs";
import { createServer } from "node:net";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { type StartOptions, type Started, startBlendworks } from "../src/mcp/start.js";
import { FakeBridge, type FakeOptions } from "./mcp-fake-bridge.js";

export async function unusedPort(): Promise<number> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return port;
}

export function scratchDir(): string {
  return mkdtempSync(join(tmpdir(), "blendworks-mcp-"));
}

export interface Harness {
  client: Client;
  started: Started;
  bridge: FakeBridge;
  close: () => Promise<void>;
}

export async function connectClient(started: Started): Promise<Client> {
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await started.server.connect(serverSide);
  const client = new Client({ name: "test-client", version: "0.0.0" });
  await client.connect(clientSide);
  return client;
}

export async function headlessHarness(fake: FakeOptions = {}, extra: Partial<StartOptions> = {}): Promise<Harness> {
  const bridge = new FakeBridge(fake);
  const started = await startBlendworks({
    workspace: join(scratchDir(), "workspace"),
    port: await unusedPort(),
    allowPython: fake.allowPython ?? false,
    startHeadless: async () => bridge.link(),
    ...extra,
  });
  const client = await connectClient(started);
  return {
    client,
    started,
    bridge,
    close: async () => {
      await client.close();
      await started.connection.close();
    },
  };
}

export async function call(client: Client, name: string, args: Record<string, unknown> = {}): Promise<CallToolResult> {
  return (await client.callTool({ name, arguments: args })) as CallToolResult;
}

export function texts(result: CallToolResult): string {
  return result.content.flatMap((item) => (item.type === "text" ? [item.text] : [])).join("\n");
}
