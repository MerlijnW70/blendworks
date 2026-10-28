import type { Server } from "@modelcontextprotocol/sdk/server/index.js";
import type { Boot } from "./boot.js";
import { BridgeConnection, type ConnectionOptions } from "./connection.js";
import { DESKTOP_ANSWER_MS, DESKTOP_SLOW_ANSWER_MS, openDesktopLink, probeDesktop } from "./desktop.js";
import type { BridgeLink } from "./protocol.js";
import type { Toolsets } from "./routing/disclosure.js";
import { type BridgeCommand, commandsFromDescribe } from "./schema.js";
import { createBootedServer, type Ready } from "./server.js";
import { Workspace } from "./workspace.js";

export interface HeadlessOptions {
  workspace: string;
  allowPython: boolean;
  autosaveSeconds?: number | "off";
}

export type StartHeadless = (options: HeadlessOptions) => Promise<BridgeLink>;

export type ConnectionTuning = Pick<ConnectionOptions, "restartDelaysMs" | "deadAfterFailures" | "failureWindowMs" | "deadCooldownMs" | "sleep" | "now">;

export interface StartOptions {
  workspace: string;
  port: number;
  allowPython: boolean;
  startHeadless: StartHeadless;
  cwd?: string;
  desktopAnswerMs?: number;
  desktopSlowAnswerMs?: number;
  timeoutFor?: (cmd: string) => number;
  progressIntervalMs?: number;
  autosaveSeconds?: number | "off";
  toolsets?: Toolsets;
  log?: (line: string) => void;
  startWaitMs?: number;
  listWaitMs?: number;
  bootBackoffMs?: number[];
  connection?: Partial<ConnectionTuning>;
}

export interface Started {
  server: Server;
  connection: BridgeConnection;
  workspace: Workspace;
  commands: BridgeCommand[];
  mode: "desktop" | "headless";
}

export interface Beginning {
  server: Server;
  workspace: Workspace;
  boot: Boot<Ready>;
  ready: Promise<Started>;
  stop: () => Promise<void>;
}

const DESKTOP_RECONNECT_MS = 5000;
const STOP_PATIENCE_MS = 2000;

function tuning(options: StartOptions): Partial<ConnectionOptions> {
  return {
    ...(options.timeoutFor === undefined ? {} : { timeoutFor: options.timeoutFor }),
    ...(options.progressIntervalMs === undefined ? {} : { progressIntervalMs: options.progressIntervalMs }),
    ...options.connection,
  };
}

export function beginBlendworks(options: StartOptions): Beginning {
  const log = options.log ?? (() => undefined);
  const workspace = Workspace.open(options.workspace, options.cwd);
  let connection: BridgeConnection | undefined;
  let mode: "desktop" | "headless" | undefined;
  let stopped = false;

  const useDesktop = (link: BridgeLink, describe: Record<string, unknown>, note: string): Ready => {
    const opened = new BridgeConnection(
      {
        open: () => openDesktopLink(options.port, DESKTOP_RECONNECT_MS, (message) => log(`blendworks: ${message}`)),
        owned: false,
        label: `desktop Blender on 127.0.0.1:${options.port}`,
        ...tuning(options),
      },
      link,
    );
    connection = opened;
    mode = "desktop";
    const commands = commandsFromDescribe(describe);
    opened.useCommands(commands);
    log(`blendworks: using ${opened.label} with ${commands.length} commands (${note}); workspace ${workspace.root} (set the add-on's workspace to the same folder, or it refuses these paths)`);
    return { connection: opened, commands };
  };

  const startHeadless = async (why: string): Promise<Ready> => {
    const headless: HeadlessOptions = {
      workspace: workspace.root,
      allowPython: options.allowPython,
      ...(options.autosaveSeconds === undefined ? {} : { autosaveSeconds: options.autosaveSeconds }),
    };
    const opened =
      connection ??
      new BridgeConnection({
        open: () => options.startHeadless(headless),
        owned: true,
        label: "headless Blender session",
        ...tuning(options),
      });
    connection = opened;
    mode = "headless";
    await opened.connect();
    const described = await opened.request("describe", {});
    const commands = commandsFromDescribe(described.result);
    opened.useCommands(commands);
    log(`blendworks: ${why}; started a headless session with ${commands.length} commands; workspace ${workspace.root}`);
    return { connection: opened, commands };
  };

  const start = async (): Promise<Ready> => {
    if (connection !== undefined && mode === "headless") return startHeadless("retrying the headless start");
    const probe = await probeDesktop(options.port, options.desktopAnswerMs ?? DESKTOP_ANSWER_MS, options.desktopSlowAnswerMs ?? DESKTOP_SLOW_ANSWER_MS, (message) => log(`blendworks: ${message}`));
    if (stopped && probe.found) await probe.link.close();
    if (stopped) throw new Error("the server was stopped while it started");
    if (probe.found) return useDesktop(probe.link, probe.describe, probe.note);
    return startHeadless(`no desktop Blender: ${probe.reason}`);
  };

  const booted = createBootedServer({
    workspace,
    starter: start,
    ...(options.toolsets === undefined ? {} : { toolsets: options.toolsets }),
    ...(options.startWaitMs === undefined ? {} : { startWaitMs: options.startWaitMs }),
    ...(options.listWaitMs === undefined ? {} : { listWaitMs: options.listWaitMs }),
    ...(options.bootBackoffMs === undefined ? {} : { bootBackoffMs: options.bootBackoffMs }),
    ...(options.connection?.now === undefined ? {} : { now: options.connection.now }),
  });
  const boot = booted.boot!;
  const ready = boot.start().then((value) => ({ server: booted.server, connection: value.connection, workspace, commands: value.commands, mode: mode! }));
  ready.catch(() => undefined);
  const stop = async () => {
    stopped = true;
    await connection?.close().catch(() => undefined);
    let timer: NodeJS.Timeout | undefined;
    const patience = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, STOP_PATIENCE_MS);
    });
    const finished = boot.start().then(
      (value) => value.connection.close(),
      () => undefined,
    );
    await Promise.race([finished, patience]);
    clearTimeout(timer);
  };
  return { server: booted.server, workspace, boot, ready, stop };
}

export async function startBlendworks(options: StartOptions): Promise<Started> {
  return beginBlendworks(options).ready;
}
