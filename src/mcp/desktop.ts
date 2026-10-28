import { connect } from "node:net";
import { LineLink } from "./line-link.js";
import type { BridgeLink } from "./protocol.js";

export const DEFAULT_PORT = 9876;
export const DESKTOP_ANSWER_MS = 1000;
export const DESKTOP_SLOW_ANSWER_MS = 6000;

export function desktopPort(env: NodeJS.ProcessEnv = process.env): number {
  const text = env["BLENDWORKS_PORT"];
  if (text === undefined || text.trim() === "") return DEFAULT_PORT;
  const port = Number(text);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`BLENDWORKS_PORT must be a port number from 1 to 65535, not "${text}"`);
  }
  return port;
}

export function openDesktopLink(port: number, timeoutMs: number, onDropped?: (message: string) => void): Promise<BridgeLink> {
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
      resolve(new LineLink(socket, socket, () => socket.destroy(), onDropped));
    });
  });
}

export type DesktopProbe =
  | { found: true; link: BridgeLink; describe: Record<string, unknown>; note: string }
  | { found: false; reason: string };

function waitFor<T>(work: Promise<T>, ms: number): Promise<T | undefined> {
  let timer: NodeJS.Timeout | undefined;
  const late = new Promise<undefined>((resolve) => {
    timer = setTimeout(() => resolve(undefined), ms);
  });
  return Promise.race([work, late]).finally(() => clearTimeout(timer));
}

export async function probeDesktop(port: number, timeoutMs = DESKTOP_ANSWER_MS, slowTimeoutMs = DESKTOP_SLOW_ANSWER_MS, onDropped?: (message: string) => void): Promise<DesktopProbe> {
  const started = Date.now();
  let link: BridgeLink;
  try {
    link = await openDesktopLink(port, timeoutMs, onDropped);
  } catch (error) {
    return { found: false, reason: `nothing answered on 127.0.0.1:${port} (${error instanceof Error ? error.message : String(error)})` };
  }
  const describing = link.call("describe", {});
  describing.catch(() => undefined);
  let describe: Record<string, unknown> | undefined;
  let note = `it answered describe within ${timeoutMs} ms`;
  try {
    describe = await waitFor(describing, Math.max(1, timeoutMs - (Date.now() - started)));
    if (describe === undefined && slowTimeoutMs > timeoutMs) {
      describe = await waitFor(describing, slowTimeoutMs - timeoutMs);
      note = `the port was open but slow: it answered describe after ${Date.now() - started} ms, on the second try`;
    }
  } catch (error) {
    await link.close();
    return { found: false, reason: `127.0.0.1:${port} is open but describe failed (${error instanceof Error ? error.message : String(error)}), so it is not a Blendworks add-on` };
  }
  if (describe !== undefined) return { found: true, link, describe, note };
  await link.close();
  return { found: false, reason: `127.0.0.1:${port} is open but gave no describe answer within ${slowTimeoutMs} ms (tried twice, ${timeoutMs} ms then ${slowTimeoutMs - timeoutMs} ms more); a busy desktop Blender is probably listening there, so a separate headless Blender is used` };
}
