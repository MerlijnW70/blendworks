import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, type CallToolResult, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import type { BridgeConnection, Progress } from "./connection.js";
import { serverInstructions } from "./instructions.js";
import { Library, libraryOptionsFromEnv } from "./library/index.js";
import { BridgeError } from "./protocol.js";
import { type Content, toContent } from "./results.js";
import type { BridgeCommand } from "./schema.js";
import { buildTools, confineArgs, listTools, takeTimeout } from "./tools.js";
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

type ProgressToken = string | number;
type Notify = (notification: { method: "notifications/progress"; params: { progressToken: ProgressToken; progress: number; total?: number; message?: string } }) => Promise<void>;

function progressReporter(token: ProgressToken | undefined, notify: Notify): ((progress: Progress) => void) | undefined {
  if (token === undefined) return undefined;
  return (progress) => {
    const elapsed = Math.round(progress.elapsedMs / 1000);
    const where = progress.state === "queued" ? `waiting behind ${progress.ahead} earlier request${progress.ahead === 1 ? "" : "s"}` : "running";
    const message = `${progress.cmd} ${where} for ${elapsed} s; it stops after ${Math.round(progress.timeoutMs / 1000)} s of running`;
    void notify({ method: "notifications/progress", params: { progressToken: token, progress: elapsed, message } }).catch(() => undefined);
  };
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

  server.setRequestHandler(CallToolRequestSchema, async (request, extra): Promise<CallToolResult> => {
    if (library.has(request.params.name)) return library.call(request.params.name, request.params.arguments ?? {}, bridge);
    const entry = tools.get(request.params.name);
    if (entry === undefined) return failure(`Unknown tool ${request.params.name}; list the tools to see the blender_ tools this Blender offers and the library_ tools.`);
    let call;
    try {
      const taken = takeTimeout(entry.command, request.params.arguments ?? {});
      call = { args: confineArgs(entry.command, taken.args, parts.workspace), timeoutMs: taken.timeoutMs };
    } catch (error) {
      return failure(explain(error));
    }
    const onProgress = progressReporter(request.params._meta?.progressToken, extra.sendNotification as Notify);
    try {
      const outcome = await parts.connection.request(entry.command.name, call.args, {
        signal: extra.signal,
        ...(call.timeoutMs === undefined ? {} : { timeoutMs: call.timeoutMs }),
        ...(onProgress === undefined ? {} : { onProgress }),
      });
      return { content: toContent(entry.command.name, outcome.result, outcome.notices) };
    } catch (error) {
      return failure(explain(error));
    }
  });

  return server;
}
