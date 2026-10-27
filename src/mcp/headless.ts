import { type Session, type SessionExit, startSession } from "../session.js";
import { type BridgeArgs, BridgeError, type BridgeLink } from "./protocol.js";
import type { HeadlessOptions } from "./start.js";

const NO_SESSION_TIMEOUT_MS = 2_147_483_647;
const STOP_GRACE_MS = 3000;

function describeExit(exit: SessionExit): string {
  return exit.signal !== null ? `Blender was stopped by ${exit.signal}` : `Blender exited with code ${exit.code}`;
}

class SessionLink implements BridgeLink {
  private exitReason: string | undefined;

  constructor(
    private readonly session: Session,
    private readonly log: (line: string) => void,
  ) {
    void session.exited.then((exit) => {
      this.exitReason = describeExit(exit);
    });
  }

  async call(cmd: string, args: BridgeArgs): Promise<Record<string, unknown>> {
    let reply;
    try {
      reply = await this.session.send(cmd, args, { timeoutMs: NO_SESSION_TIMEOUT_MS });
    } catch (error) {
      await this.session.exited;
      this.log(`blendworks: ${this.exitReason ?? "Blender exited"}; its last output:\n${this.session.stderrTail().slice(-2000)}`);
      throw new BridgeError("disconnected", this.exitReason ?? (error instanceof Error ? error.message : String(error)));
    }
    if (!reply.ok) throw new BridgeError(reply.error.code, reply.error.message);
    return reply.result;
  }

  async close(): Promise<void> {
    await this.session.close(STOP_GRACE_MS);
  }

  async kill(): Promise<void> {
    await this.session.kill();
  }

  onClose(listener: (reason: string) => void): void {
    void this.session.exited.then((exit) => listener(describeExit(exit)));
  }
}

export async function startHeadlessSession(options: HeadlessOptions, log: (line: string) => void = () => undefined): Promise<BridgeLink> {
  const session = await startSession({
    workspace: options.workspace,
    allowPython: options.allowPython,
    timeoutMs: NO_SESSION_TIMEOUT_MS,
    ...(options.autosaveSeconds === undefined ? {} : { autosaveSeconds: options.autosaveSeconds }),
  });
  return new SessionLink(session, log);
}
