import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { BridgeConnection } from "./connection.js";
import { DESKTOP_ANSWER_MS, openDesktopLink, probeDesktop } from "./desktop.js";
import type { BridgeLink } from "./protocol.js";
import { type BridgeCommand, commandsFromDescribe } from "./schema.js";
import { createServer } from "./server.js";
import { Workspace } from "./workspace.js";

export interface HeadlessOptions {
  workspace: string;
  allowPython: boolean;
  autosaveSeconds?: number | "off";
}

export type StartHeadless = (options: HeadlessOptions) => Promise<BridgeLink>;

export interface StartOptions {
  workspace: string;
  port: number;
  allowPython: boolean;
  startHeadless: StartHeadless;
  cwd?: string;
  desktopAnswerMs?: number;
  timeoutFor?: (cmd: string) => number;
  progressIntervalMs?: number;
  autosaveSeconds?: number | "off";
  log?: (line: string) => void;
}

export interface Started {
  server: Server;
  connection: BridgeConnection;
  workspace: Workspace;
  commands: BridgeCommand[];
  mode: "desktop" | "headless";
}

const DESKTOP_RECONNECT_MS = 5000;

function tuning(options: StartOptions): { timeoutFor?: (cmd: string) => number; progressIntervalMs?: number } {
  return {
    ...(options.timeoutFor === undefined ? {} : { timeoutFor: options.timeoutFor }),
    ...(options.progressIntervalMs === undefined ? {} : { progressIntervalMs: options.progressIntervalMs }),
  };
}

export async function startBlendworks(options: StartOptions): Promise<Started> {
  const log = options.log ?? (() => undefined);
  const workspace = Workspace.open(options.workspace, options.cwd);
  const desktop = await probeDesktop(options.port, options.desktopAnswerMs ?? DESKTOP_ANSWER_MS);
  if (desktop !== undefined) {
    const connection = new BridgeConnection(
      {
        open: () => openDesktopLink(options.port, DESKTOP_RECONNECT_MS),
        owned: false,
        label: `desktop Blender on 127.0.0.1:${options.port}`,
        ...tuning(options),
      },
      desktop.link,
    );
    const commands = commandsFromDescribe(desktop.describe);
    connection.useCommands(commands);
    log(`blendworks: using ${connection.label} with ${commands.length} commands; workspace ${workspace.root} (set the add-on's workspace to the same folder, or it refuses these paths)`);
    return { server: createServer({ connection, workspace, commands }), connection, workspace, commands, mode: "desktop" };
  }
  const headless: HeadlessOptions = {
    workspace: workspace.root,
    allowPython: options.allowPython,
    ...(options.autosaveSeconds === undefined ? {} : { autosaveSeconds: options.autosaveSeconds }),
  };
  const connection = new BridgeConnection({
    open: () => options.startHeadless(headless),
    owned: true,
    label: "headless Blender session",
    ...tuning(options),
  });
  await connection.connect();
  const described = await connection.request("describe", {});
  const commands = commandsFromDescribe(described.result);
  connection.useCommands(commands);
  log(`blendworks: no desktop Blender answered on 127.0.0.1:${options.port}; started a headless session with ${commands.length} commands; workspace ${workspace.root}`);
  return { server: createServer({ connection, workspace, commands }), connection, workspace, commands, mode: "headless" };
}
