import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { CallToolResult, Tool } from "@modelcontextprotocol/sdk/types.js";
import { startHeadlessSession } from "../../src/mcp/headless.js";
import type { BridgeCommand } from "../../src/mcp/schema.js";
import { createServer as createMcpServer, type ServerParts } from "../../src/mcp/server.js";
import { type StartHeadless, startBlendworks } from "../../src/mcp/start.js";

export interface Listing {
  tools: Tool[];
  instructions: string;
}

export interface BenchServer {
  commands: BridgeCommand[];
  connect(name: string, extra?: Partial<ServerParts>): Promise<BenchClient>;
  close(): Promise<void>;
}

export interface BenchClient {
  listing(): Promise<Listing>;
  call(name: string, args: Record<string, unknown>): Promise<CallToolResult>;
  close(): Promise<void>;
}

async function unusedPort(): Promise<number> {
  const server = createServer();
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  await new Promise<void>((resolve) => server.close(() => resolve()));
  return port;
}

async function attach(parts: ServerParts, name: string): Promise<Client> {
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await createMcpServer(parts).connect(serverSide);
  const client = new Client({ name, version: "0.0.0" });
  await client.connect(clientSide);
  return client;
}

export async function startBenchServer(startHeadless: StartHeadless = (headless) => startHeadlessSession(headless)): Promise<BenchServer> {
  const folder = mkdtempSync(join(tmpdir(), "blendworks-bench-"));
  const workspace = join(folder, "workspace");
  const port = await unusedPort();
  const base = await startBlendworks({ workspace, port, allowPython: true, startHeadless });
  return {
    commands: base.commands,
    async connect(name, extra = {}) {
      const client = await attach({ connection: base.connection, workspace: base.workspace, commands: base.commands, ...extra }, name);
      return {
        async listing() {
          const { tools } = await client.listTools();
          return { tools, instructions: client.getInstructions() ?? "" };
        },
        async call(tool, args) {
          return (await client.callTool({ name: tool, arguments: args })) as CallToolResult;
        },
        async close() {
          await client.close();
        },
      };
    },
    async close() {
      await base.connection.close().catch(() => undefined);
      rmSync(folder, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    },
  };
}
