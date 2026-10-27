import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { type BridgeArgs, BridgeError } from "./protocol.js";
import type { BridgeCommand } from "./schema.js";
import type { Workspace } from "./workspace.js";

export const TOOL_PREFIX = "blender_";
export const RUN_PYTHON = "run_python";
export const TIMEOUT_FIELD = "timeout_seconds";

export const RUN_PYTHON_WARNING =
  "DANGEROUS: runs arbitrary Python code inside Blender, with the same access to files, network and programs as the user running it. Use it only when no other blender_ tool can do the step.";

export interface ToolEntry {
  tool: Tool;
  command: BridgeCommand;
}

export interface ToolCall {
  args: BridgeArgs;
  timeoutMs: number | undefined;
}

export function toolName(command: string): string {
  return `${TOOL_PREFIX}${command}`;
}

function describeTool(command: BridgeCommand): string {
  if (command.name === RUN_PYTHON) return `${RUN_PYTHON_WARNING} ${command.description}`;
  if (command.dangerous) return `DANGEROUS: ${command.description}`;
  return command.description;
}

export function annotations(command: BridgeCommand): NonNullable<Tool["annotations"]> {
  const readOnly = !command.mutates && !command.writesFiles && !command.destructive && !command.dangerous;
  const derived: NonNullable<Tool["annotations"]> = {
    readOnlyHint: readOnly,
    destructiveHint: command.destructive,
    idempotentHint: readOnly,
    openWorldHint: command.dangerous,
  };
  if (command.name === RUN_PYTHON) derived.title = "Run arbitrary Python in Blender";
  return derived;
}

function wholeSeconds(ms: number): number {
  return Math.round(ms / 100) / 10;
}

function withTimeoutField(command: BridgeCommand): Tool["inputSchema"] {
  const properties = { ...((command.inputSchema["properties"] as Record<string, unknown> | undefined) ?? {}) };
  if (TIMEOUT_FIELD in properties) throw new Error(`${command.name} already has a ${TIMEOUT_FIELD} field`);
  properties[TIMEOUT_FIELD] = {
    type: "number",
    description: `Seconds to wait for Blender before this call is stopped. Default ${wholeSeconds(command.timeoutMs)}, at most ${wholeSeconds(command.maxTimeoutMs)}.`,
    exclusiveMinimum: 0,
    maximum: wholeSeconds(command.maxTimeoutMs),
  };
  return { ...command.inputSchema, properties } as Tool["inputSchema"];
}

export function buildTools(commands: BridgeCommand[]): Map<string, ToolEntry> {
  const tools = new Map<string, ToolEntry>();
  for (const command of commands) {
    if (command.internal) continue;
    const tool: Tool = {
      name: toolName(command.name),
      description: describeTool(command),
      inputSchema: withTimeoutField(command),
      annotations: annotations(command),
    };
    tools.set(tool.name, { tool, command });
  }
  return tools;
}

export function takeTimeout(command: BridgeCommand, args: BridgeArgs): ToolCall {
  const { [TIMEOUT_FIELD]: requested, ...rest } = args;
  if (requested === undefined || requested === null) return { args: rest, timeoutMs: undefined };
  const limit = wholeSeconds(command.maxTimeoutMs);
  if (typeof requested !== "number" || !Number.isFinite(requested) || requested <= 0 || requested > limit) {
    throw new BridgeError("bad_args", `${TIMEOUT_FIELD} must be a number of seconds above 0 and at most ${limit} for ${command.name}`);
  }
  return { args: rest, timeoutMs: Math.round(requested * 1000) };
}

export function confineArgs(command: BridgeCommand, args: BridgeArgs, workspace: Workspace): BridgeArgs {
  const confined: BridgeArgs = { ...args };
  for (const field of command.pathFields) {
    if (confined[field] === undefined || confined[field] === null) continue;
    confined[field] = workspace.resolve(confined[field]);
  }
  return confined;
}

export function listTools(bridgeTools: Map<string, ToolEntry>, libraryTools: Tool[]): Tool[] {
  const listed = [...bridgeTools.values()].map((entry) => entry.tool);
  for (const tool of libraryTools) {
    if (bridgeTools.has(tool.name)) throw new Error(`the tool name ${tool.name} is taken twice`);
    listed.push(tool);
  }
  return listed;
}
