import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { BridgeArgs } from "./protocol.js";
import type { BridgeCommand } from "./schema.js";
import type { Workspace } from "./workspace.js";

export const TOOL_PREFIX = "blender_";
export const RUN_PYTHON = "run_python";
const NOT_TOOLS = new Set(["describe"]);
const READ_ONLY = new Set(["scene_info", "uv_info", "render_preview", "image_info"]);

export const RUN_PYTHON_WARNING =
  "DANGEROUS: runs arbitrary Python code inside Blender, with the same access to files, network and programs as the user running it. Use it only when no other blender_ tool can do the step.";

export interface ToolEntry {
  tool: Tool;
  command: BridgeCommand;
}

export function toolName(command: string): string {
  return `${TOOL_PREFIX}${command}`;
}

function isDangerous(command: BridgeCommand): boolean {
  return command.dangerous || command.name === RUN_PYTHON;
}

function describeTool(command: BridgeCommand): string {
  if (command.name === RUN_PYTHON) return `${RUN_PYTHON_WARNING} ${command.description}`;
  if (command.dangerous) return `DANGEROUS: ${command.description}`;
  return command.description;
}

function annotations(command: BridgeCommand): Tool["annotations"] {
  if (isDangerous(command)) return { title: command.name === RUN_PYTHON ? "Run arbitrary Python in Blender" : command.name, destructiveHint: true, openWorldHint: true, readOnlyHint: false };
  if (READ_ONLY.has(command.name)) return { readOnlyHint: true, openWorldHint: false };
  return { readOnlyHint: false, destructiveHint: false, openWorldHint: false };
}

export function buildTools(commands: BridgeCommand[]): Map<string, ToolEntry> {
  const tools = new Map<string, ToolEntry>();
  for (const command of commands) {
    if (NOT_TOOLS.has(command.name)) continue;
    const tool: Tool = {
      name: toolName(command.name),
      description: describeTool(command),
      inputSchema: command.inputSchema,
      annotations: annotations(command),
    };
    tools.set(tool.name, { tool, command });
  }
  return tools;
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
