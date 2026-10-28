import { Worker } from "node:worker_threads";

export const HEARTBEAT_MS = 2_000;
export const STALE_AFTER_MS = 30_000;

const WORKER_SOURCE = `
const { parentPort } = require("node:worker_threads");
const { utimesSync } = require("node:fs");
const paths = new Set();
parentPort.on("message", (message) => {
  if (message.add !== undefined) paths.add(message.add);
  else paths.delete(message.remove);
});
setInterval(() => {
  const now = new Date();
  for (const path of paths) {
    try {
      utimesSync(path, now, now);
    } catch {
      paths.delete(path);
    }
  }
}, ${HEARTBEAT_MS});
`;

let worker: Worker | undefined;

function beat(message: { add: string } | { remove: string }): void {
  if (worker === undefined) {
    worker = new Worker(WORKER_SOURCE, { eval: true });
    worker.unref();
    worker.on("error", () => {
      worker = undefined;
    });
  }
  worker.postMessage(message);
}

export function trackHeartbeat(path: string): void {
  beat({ add: path });
}

export function untrackHeartbeat(path: string): void {
  if (worker !== undefined) worker.postMessage({ remove: path });
}
