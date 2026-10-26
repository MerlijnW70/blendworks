import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, type CallToolResult, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import type { BridgeConnection } from "./connection.js";
import { serverInstructions } from "./instructions.js";
import { Library, libraryOptionsFromEnv } from "./library/index.js";
import { BridgeError } from "./protocol.js";
import { type Content, toContent } from "./results.js";
import type { BridgeCommand } from "./schema.js";
import { buildTools, confineArgs, listTools } from "./tools.js";
import { type Workspace, WorkspaceError } from "./workspace.js";

export const SERVER_NAME = "blendworks";
export const SERVER_VERSION = "0.0.0";

export interface ServerParts {
  connection: BridgeConnection;
  workspace: Workspace;
  commands: BridgeCommand[];
  library?: Library;
}

function failure(text: string, before: Content[] = []): CallToolResult {
  return { content: [...before, { type: "text", text }], isError: true };
}

function explain(error: unknown): string {
  if (error instanceof WorkspaceError) return `Refused: ${error.message}`;
  if (error instanceof BridgeError) return `${error.code}: ${error.message}`;
  return `failed: ${error instanceof Error ? error.message : String(error)}`;
}

export function createServer(parts: ServerParts): Server {
  const tools = buildTools(parts.commands);
  const library = parts.library ?? new Library({ workspace: parts.workspace, ...libraryOptionsFromEnv(process.env) });
  const listed = listTools(tools, library.tools);
  const bridge = { commands: parts.commands, request: (cmd: string, args: Record<string, unknown>) => parts.connection.request(cmd, args) };
  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {} }, instructions: serverInstructions(parts.workspace.root) },
  );

  server.setRequestHandler(ListToolsRequestSchema, () => ({ tools: listed }));

  server.setRequestHandler(CallToolRequestSchema, async (request): Promise<CallToolResult> => {
    if (library.has(request.params.name)) return library.call(request.params.name, request.params.arguments ?? {}, bridge);
    const entry = tools.get(request.params.name);
    if (entry === undefined) return failure(`Unknown tool ${request.params.name}; list the tools to see the blender_ tools this Blender offers and the library_ tools.`);
    let args;
    try {
      args = confineArgs(entry.command, request.params.arguments ?? {}, parts.workspace);
    } catch (error) {
      return failure(explain(error));
    }
    try {
      const outcome = await parts.connection.request(entry.command.name, args);
      return { content: toContent(entry.command.name, outcome.result, outcome.notices) };
    } catch (error) {
      return failure(explain(error));
    }
  });

  return server;
}
