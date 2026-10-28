import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, type CallToolResult, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { Boot } from "./boot.js";
import type { BridgeConnection, Progress } from "./connection.js";
import { badArguments, START_HINT } from "./errors.js";
import { serverInstructions } from "./instructions.js";
import { Library, libraryOptionsFromEnv } from "./library/index.js";
import { BridgeError } from "./protocol.js";
import { type Content, toContent } from "./results.js";
import { type ResolvedToolsets, resolveToolsets, type Toolsets } from "./routing/disclosure.js";
import { CALL_TOOL, SEARCH_TOOL, toolNameOf } from "./routing/names.js";
import { find, readFindArgs } from "./routing/router.js";
import { type BridgeCommand, FALLBACK_TIMEOUT_MS } from "./schema.js";
import { buildSurface, type Surface } from "./surface.js";
import { confineArgs, TIMEOUT_FIELD, takeTimeout } from "./tools.js";
import { type Workspace, WorkspaceError } from "./workspace.js";

export const SERVER_NAME = "blendworks";
export const SERVER_VERSION = "0.0.0";
const MAX_CALL_NESTING = 3;
export const LIST_WAIT_MS = 10_000;

export interface Ready {
  connection: BridgeConnection;
  commands: BridgeCommand[];
}

export interface ServerParts {
  workspace: Workspace;
  connection?: BridgeConnection;
  commands?: BridgeCommand[];
  starter?: () => Promise<Ready>;
  startWaitMs?: number;
  listWaitMs?: number;
  bootBackoffMs?: number[];
  now?: () => number;
  library?: Library;
  toolsets?: Toolsets;
}

export interface BootedServer {
  server: Server;
  boot: Boot<Ready> | undefined;
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

function isLibraryOnly(name: string): boolean {
  return name.startsWith("library_") && name !== "library_apply";
}

function needsBlender(name: string, args: Record<string, unknown>): boolean {
  if (name === CALL_TOOL) return !isLibraryOnly(toolNameOf(String(args["tool"] ?? "").trim()));
  return !isLibraryOnly(name);
}

function waitFromArgs(args: Record<string, unknown>, fallbackMs: number): number {
  const inner = isRecord(args["arguments"]) ? args["arguments"] : {};
  const requested = args[TIMEOUT_FIELD] ?? inner[TIMEOUT_FIELD];
  return typeof requested === "number" && requested > 0 ? Math.round(requested * 1000) : fallbackMs;
}

export function createServer(parts: ServerParts): Server {
  return createBootedServer(parts).server;
}

export function createBootedServer(parts: ServerParts): BootedServer {
  const library = parts.library ?? new Library({ workspace: parts.workspace, ...libraryOptionsFromEnv(process.env) });
  const toolsets = parts.toolsets ?? { kind: "auto" };
  let connection = parts.connection;
  let surface: Surface = buildSurface(parts.commands ?? [], library.tools, toolsets);
  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: { listChanged: true } }, instructions: serverInstructions(parts.workspace.root) },
  );
  const announce = () => void server.sendToolListChanged().catch(() => undefined);
  const starter = parts.starter;
  const boot =
    starter === undefined
      ? undefined
      : new Boot<Ready>({
          start: async () => {
            const ready = await starter();
            surface = buildSurface(ready.commands, library.tools, toolsets);
            connection = ready.connection;
            announce();
            return ready;
          },
          ...(parts.bootBackoffMs === undefined ? {} : { backoffMs: parts.bootBackoffMs }),
          ...(parts.now === undefined ? {} : { now: parts.now }),
        });
  boot?.start().catch(() => undefined);
  let resolved: ResolvedToolsets | undefined;
  const current = (): ResolvedToolsets => (resolved ??= resolveToolsets(toolsets, server.getClientVersion()?.name));
  const reveal = (names: string[]) => {
    if (surface.disclosure.activate(names, current())) announce();
  };

  const suggest = (name: string): string => {
    const near = surface.search.search(name.replace(/^(blender|library)_/, "").replace(/_/g, " "), { limit: 3 }).map((match) => match.name);
    return near.length === 0 ? "" : ` Did you mean ${near.join(", ")}?`;
  };

  const awaitBlender = async (name: string, args: Record<string, unknown>): Promise<CallToolResult | undefined> => {
    if (boot === undefined || boot.ready !== undefined || !needsBlender(name, args)) return undefined;
    try {
      await boot.wait(waitFromArgs(args, parts.startWaitMs ?? FALLBACK_TIMEOUT_MS), "Blender");
      return undefined;
    } catch (error) {
      if (error instanceof BridgeError && error.code === "timeout") return failure(explain(error));
      return failure(error instanceof BridgeError ? `${explain(error)}. ${START_HINT}` : explain(error));
    }
  };

  const bridgeAccess = () => {
    const live = connection!;
    return { commands: surface.commands, request: (cmd: string, args: Record<string, unknown>, options?: { signal?: AbortSignal }) => live.request(cmd, args, options) };
  };

  const runBridge = async (name: string, args: Record<string, unknown>, context: CallContext): Promise<CallToolResult> => {
    const entry = surface.tools.get(name)!;
    let call;
    try {
      const taken = takeTimeout(entry.command, args);
      call = { args: confineArgs(entry.command, taken.args, parts.workspace), timeoutMs: taken.timeoutMs };
    } catch (error) {
      return failure(explain(error));
    }
    const onProgress = progressReporter(context.progressToken, context.notify);
    try {
      const outcome = await connection!.request(entry.command.name, call.args, {
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
    const waited = await awaitBlender(requested, args);
    if (waited !== undefined) return waited;
    const name = surface.disclosure.has(requested) ? requested : toolNameOf(requested);
    if (!surface.disclosure.has(name)) return failure(`Unknown tool ${name}; find tools with ${SEARCH_TOOL}, or list the tools.${suggest(name)}`);
    const listed = surface.disclosure.listedNames(current()).has(name);
    if (throughCall || !listed) {
      const problems = surface.check.problems(name, args);
      if (problems.length > 0) return failure(badArguments(name, problems, surface.disclosure.route(name)!.tool.inputSchema));
      reveal([name]);
    }
    if (library.has(name)) return library.call(name, args, bridgeAccess(), context.signal);
    return runBridge(name, args, context);
  };

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    await boot?.settle(parts.listWaitMs ?? LIST_WAIT_MS);
    return { tools: surface.disclosure.listing(current()) };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request, extra): Promise<CallToolResult> => {
    const name = request.params.name;
    const args = request.params.arguments ?? {};
    const context: CallContext = { signal: extra.signal, notify: extra.sendNotification as Notify, progressToken: request.params._meta?.progressToken };
    if (name === SEARCH_TOOL) {
      const waited = await awaitBlender(name, args);
      if (waited !== undefined) return waited;
      const read = readFindArgs(args, new Set(surface.families));
      if (typeof read === "string") return failure(`bad_args: ${SEARCH_TOOL}: ${read}`);
      const found = find(surface.search, read);
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

  return { server, boot };
}
