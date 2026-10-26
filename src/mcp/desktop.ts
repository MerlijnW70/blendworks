import { connect } from "node:net";
import { LineLink } from "./line-link.js";
import type { BridgeLink } from "./protocol.js";

export const DEFAULT_PORT = 9876;
export const DESKTOP_ANSWER_MS = 1000;

export function desktopPort(env: NodeJS.ProcessEnv = process.env): number {
  const text = env["BLENDWORKS_PORT"];
  if (text === undefined || text.trim() === "") return DEFAULT_PORT;
  const port = Number(text);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`BLENDWORKS_PORT must be a port number from 1 to 65535, not "${text}"`);
  }
  return port;
}

export function openDesktopLink(port: number, timeoutMs: number): Promise<BridgeLink> {
  return new Promise((resolve, reject) => {
    const socket = connect({ host: "127.0.0.1", port });
    const timer = setTimeout(() => {
      socket.destroy();
      reject(new Error(`no answer on 127.0.0.1:${port} within ${timeoutMs} ms`));
    }, timeoutMs);
    socket.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    socket.once("connect", () => {
      clearTimeout(timer);
      socket.setNoDelay(true);
      resolve(new LineLink(socket, socket, () => socket.destroy()));
    });
  });
}

export async function probeDesktop(port: number, timeoutMs = DESKTOP_ANSWER_MS): Promise<{ link: BridgeLink; describe: Record<string, unknown> } | undefined> {
  const started = Date.now();
  let link: BridgeLink;
  try {
    link = await openDesktopLink(port, timeoutMs);
  } catch {
    return undefined;
  }
  const remaining = Math.max(1, timeoutMs - (Date.now() - started));
  let timer: NodeJS.Timeout | undefined;
  const late = new Promise<undefined>((resolve) => {
    timer = setTimeout(() => resolve(undefined), remaining);
  });
  try {
    const describe = await Promise.race([link.call("describe", {}), late]);
    if (describe !== undefined) return { link, describe };
  } catch {
    return closeAndForget(link);
  } finally {
    clearTimeout(timer);
  }
  return closeAndForget(link);
}

async function closeAndForget(link: BridgeLink): Promise<undefined> {
  await link.close();
  return undefined;
}
