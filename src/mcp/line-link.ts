import type { Readable, Writable } from "node:stream";
import { createInterface } from "node:readline";
import { type BridgeArgs, BridgeError, type BridgeLink, parseReply } from "./protocol.js";

interface Pending {
  resolve: (result: Record<string, unknown>) => void;
  reject: (error: Error) => void;
}

export class LineLink implements BridgeLink {
  private nextId = 1;
  private readonly pending = new Map<number, Pending>();
  private readonly closeListeners: ((reason: string) => void)[] = [];
  private closedReason: string | undefined;

  constructor(
    input: Readable,
    private readonly output: Writable,
    private readonly shutdown: () => void,
  ) {
    const lines = createInterface({ input, crlfDelay: Infinity });
    lines.on("line", (line) => this.receive(line));
    input.on("close", () => this.markClosed("the bridge closed the connection"));
    input.on("error", (error) => this.markClosed(`the bridge connection failed: ${error.message}`));
    output.on("error", (error) => this.markClosed(`the bridge connection failed: ${error.message}`));
  }

  call(cmd: string, args: BridgeArgs): Promise<Record<string, unknown>> {
    if (this.closedReason !== undefined) return Promise.reject(new BridgeError("disconnected", this.closedReason));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.output.write(`${JSON.stringify({ id, cmd, args })}\n`);
    });
  }

  async close(): Promise<void> {
    this.markClosed("the connection was closed");
    this.shutdown();
  }

  onClose(listener: (reason: string) => void): void {
    if (this.closedReason !== undefined) listener(this.closedReason);
    else this.closeListeners.push(listener);
  }

  private receive(line: string): void {
    if (line.trim() === "") return;
    let reply;
    try {
      reply = parseReply(line);
    } catch {
      return;
    }
    const waiting = this.pending.get(reply.id);
    if (waiting === undefined) return;
    this.pending.delete(reply.id);
    if (reply.ok) waiting.resolve(reply.result);
    else waiting.reject(new BridgeError(reply.error.code, reply.error.message));
  }

  private markClosed(reason: string): void {
    if (this.closedReason !== undefined) return;
    this.closedReason = reason;
    for (const waiting of this.pending.values()) waiting.reject(new BridgeError("disconnected", reason));
    this.pending.clear();
    for (const listener of this.closeListeners.splice(0)) listener(reason);
  }
}
