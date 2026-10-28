import type { EventEmitter } from "node:events";

export interface Guards {
  shutdown: (exitCode: number) => Promise<void>;
  killChildren: () => void;
  log: (line: string) => void;
}

function describe(reason: unknown): string {
  return reason instanceof Error ? (reason.stack ?? reason.message) : String(reason);
}

export function installProcessGuards(target: EventEmitter, guards: Guards): void {
  let failing = false;
  const fail = (what: string) => (reason: unknown) => {
    guards.log(`blendworks: ${what}: ${describe(reason)}`);
    if (failing) return;
    failing = true;
    void guards.shutdown(1).catch(() => undefined);
  };
  target.on("unhandledRejection", fail("unhandled rejection"));
  target.on("uncaughtException", fail("uncaught exception"));
  target.on("exit", () => guards.killChildren());
}
