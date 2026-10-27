import { vi } from "vitest";
import type { Slot } from "../../scripts/lib/slots.js";
import { isBlenderCommand, takeSlot, untilProcessExits, whileProcessRuns, whileProcessRunsSync } from "./slot.js";

vi.mock("node:child_process", async (importOriginal) => {
  const original = await importOriginal<typeof import("node:child_process")>();
  const slotted = <Run extends (command: string, ...rest: never[]) => unknown>(run: Run): Run =>
    ((command: string, ...rest: never[]) => (isBlenderCommand(command) ? whileProcessRunsSync(() => run(command, ...rest)) : run(command, ...rest))) as Run;
  return { ...original, execFileSync: slotted(original.execFileSync), spawnSync: slotted(original.spawnSync) };
});

vi.mock("../../src/session.js", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../src/session.js")>();
  return {
    ...original,
    startSession: (options?: Parameters<typeof original.startSession>[0]) => untilProcessExits(() => original.startSession(options), (session) => session.exited),
  };
});

vi.mock("../../src/judge/sandbox.js", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../src/judge/sandbox.js")>();
  return { ...original, runSandboxed: (...args: Parameters<typeof original.runSandboxed>) => whileProcessRuns(() => original.runSandboxed(...args)) };
});

vi.mock("@modelcontextprotocol/sdk/client/stdio.js", async (importOriginal) => {
  const original = await importOriginal<typeof import("@modelcontextprotocol/sdk/client/stdio.js")>();
  class SlottedStdioTransport extends original.StdioClientTransport {
    private readonly startsBlender: boolean;
    private slot: Slot | undefined;

    constructor(server: ConstructorParameters<typeof original.StdioClientTransport>[0]) {
      super(server);
      this.startsBlender = server.env?.["BLENDER"] !== undefined;
    }

    override async start(): Promise<void> {
      if (this.startsBlender) this.slot = await takeSlot();
      try {
        await super.start();
      } catch (error) {
        this.slot?.release();
        throw error;
      }
    }

    override async close(): Promise<void> {
      try {
        await super.close();
      } finally {
        this.slot?.release();
      }
    }
  }
  return { ...original, StdioClientTransport: SlottedStdioTransport };
});
