import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, type CallToolResult, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import type { BridgeConnection, Progress } from "./connection.js";
import { serverInstructions } from "./instructions.js";
import { Library, libraryOptionsFromEnv } from "./library/index.js";
import { BridgeError } from "./protocol.js";
import { type Content, toContent } from "./results.js";
import { libraryTool, routesFor } from "./routing/catalog.js";
import { Disclosure, type ResolvedToolsets, resolveToolsets, type Toolsets, TOOLSETS_USAGE, unknownFamilies } from "./routing/disclosure.js";
import { CALL_TOOL, SEARCH_TOOL, toolNameOf } from "./routing/names.js";
import { find, readFindArgs, routerTools } from "./routing/router.js";
import { ToolSearch } from "./routing/search.js";
import { ArgumentCheck } from "./routing/validate.js";
import type { BridgeCommand } from "./schema.js";
import { buildTools, confineArgs, listTools, takeTimeout } from "./tools.js";
import { type Workspace, WorkspaceError } from "./workspace.js";

export const SERVER_NAME = "blendworks";
export const SERVER_VERSION = "0.0.0";
const MAX_CALL_NESTING = 3;

export interface ServerParts {
  connection: BridgeConnection;
  workspace: Workspace;
  commands: BridgeCommand[];
  library?: Library;
  toolsets?: Toolsets;
}

function failure(text: string, before: Content[] = []): CallToolResult {
  return { content: [...before, { type: "text", text }], isError: true };
}

type ProgressToken = string | number;
type Notify = (notification: { method: "notifications/progress"; params: { progressToken: ProgressToken; progress: number; total?: number; message?: string } }) => Promise<void>;
type CallContext = { signal: AbortSignal; notify: Notify; progressToken: ProgressToken | undefined };

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function createServer(parts: ServerParts): Server {
  const tools = buildTools(parts.commands);
  const library = parts.library ?? new Library({ workspace: parts.workspace, ...libraryOptionsFromEnv(process.env) });
  const libraryTools = library.tools.map(libraryTool);
  listTools(tools, libraryTools);
  const routes = routesFor(tools, libraryTools);
  const toolsets = parts.toolsets ?? { kind: "auto" };
  const strange = unknownFamilies(toolsets, routes);
  if (strange.length > 0) throw new Error(`--toolsets names unknown families ${strange.join(", ")}; use ${TOOLSETS_USAGE}, with the families ${[...new Set(routes.map((route) => route.family))].sort().join(", ")}`);
  const families = [...new Set(routes.map((route) => route.family))].sort();
  const disclosure = new Disclosure(routes, routerTools(families));
  const search = new ToolSearch(routes);
  const check = new ArgumentCheck(new Map(routes.map((route) => [route.name, route.tool.inputSchema])));
  const bridge = { commands: parts.commands, request: (cmd: string, args: Record<string, unknown>) => parts.connection.request(cmd, args) };
  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: { listChanged: true } }, instructions: serverInstructions(parts.workspace.root) },
  );
  let resolved: ResolvedToolsets | undefined;
  const current = (): ResolvedToolsets => (resolved ??= resolveToolsets(toolsets, server.getClientVersion()?.name));
  const reveal = (names: string[]) => {
    if (disclosure.activate(names, current())) void server.sendToolListChanged().catch(() => undefined);
  };

  const suggest = (name: string): string => {
    const near = search.search(name.replace(/^(blender|library)_/, "").replace(/_/g, " "), { limit: 3 }).map((match) => match.name);
    return near.length === 0 ? "" : ` Did you mean ${near.join(", ")}?`;
  };

  const runBridge = async (name: string, args: Record<string, unknown>, context: CallContext): Promise<CallToolResult> => {
    const entry = tools.get(name)!;
    let call;
    try {
      const taken = takeTimeout(entry.command, args);
      call = { args: confineArgs(entry.command, taken.args, parts.workspace), timeoutMs: taken.timeoutMs };
    } catch (error) {
      return failure(explain(error));
    }
    const onProgress = progressReporter(context.progressToken, context.notify);
    try {
      const outcome = await parts.connection.request(entry.command.name, call.args, {
        signal: context.signal,
        ...(call.timeoutMs === undefined ? {} : { timeoutMs: call.timeoutMs }),
        ...(onProgress === undefined ? {} : { onProgress }),
      });
      return { content: toContent(entry.command.name, outcome.result, outcome.notices) };
    } catch (error) {
      return failure(explain(error));
    }
  };

  const invoke = async (requested: string, args: Record<string, unknown>, context: CallContext, throughCall: boolean): Promise<CallToolResult> => {
    const name = disclosure.has(requested) ? requested : toolNameOf(requested);
    if (!disclosure.has(name)) return failure(`Unknown tool ${name}; find tools with ${SEARCH_TOOL}, or list the tools.${suggest(name)}`);
    const listed = disclosure.listedNames(current()).has(name);
    if (throughCall || !listed) {
      const problems = check.problems(name, args);
      if (problems.length > 0) return failure(`bad_args: ${name} refused these arguments: ${problems.join("; ")}. Its schema: ${JSON.stringify(disclosure.route(name)!.tool.inputSchema)}`);
      reveal([name]);
    }
    if (library.has(name)) return library.call(name, args, bridge);
    return runBridge(name, args, context);
  };

  server.setRequestHandler(ListToolsRequestSchema, () => ({ tools: disclosure.listing(current()) }));

  server.setRequestHandler(CallToolRequestSchema, async (request, extra): Promise<CallToolResult> => {
    const name = request.params.name;
    const args = request.params.arguments ?? {};
    const context: CallContext = { signal: extra.signal, notify: extra.sendNotification as Notify, progressToken: request.params._meta?.progressToken };
    if (name === SEARCH_TOOL) {
      const read = readFindArgs(args, new Set(families));
      if (typeof read === "string") return failure(`bad_args: ${SEARCH_TOOL}: ${read}`);
      const found = find(search, read);
      reveal(found.names);
      return found.result;
    }
    if (name === CALL_TOOL) {
      let request: Record<string, unknown> = args;
      for (let depth = 0; depth < MAX_CALL_NESTING; depth += 1) {
        const target = request["tool"];
        const inner = request["arguments"] ?? {};
        const unknown = Object.keys(request).filter((key) => key !== "tool" && key !== "arguments");
        if (typeof target !== "string" || target.trim() === "" || unknown.length > 0) return failure(`bad_args: ${CALL_TOOL} takes tool (a tool name) and arguments (an object)${unknown.length > 0 ? `, not ${unknown.join(", ")}` : ""}`);
        if (!isRecord(inner)) return failure(`bad_args: ${CALL_TOOL}: arguments must be an object`);
        const resolvedName = toolNameOf(target.trim());
        if (resolvedName === SEARCH_TOOL) return failure(`bad_args: call ${SEARCH_TOOL} directly, not through ${CALL_TOOL}`);
        if (resolvedName !== CALL_TOOL) return invoke(resolvedName, inner, context, true);
        request = inner;
      }
      return failure(`bad_args: ${CALL_TOOL} nests ${CALL_TOOL} too deeply`);
    }
    return invoke(name, args, context, false);
  });

  return server;
}
