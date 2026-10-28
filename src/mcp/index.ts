import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { killLiveSessions } from "../session.js";
import { desktopPort } from "./desktop.js";
import { startHeadlessSession } from "./headless.js";
import { installProcessGuards } from "./hygiene.js";
import { parseOptions, USAGE } from "./options.js";
import { beginBlendworks } from "./start.js";

async function main(): Promise<void> {
  const options = parseOptions(process.argv.slice(2));
  if (options.help) {
    console.error(USAGE);
    return;
  }
  const timeoutMs = options.timeoutMs;
  const log = (line: string) => console.error(line);
  const begun = beginBlendworks({
    workspace: options.workspace,
    port: desktopPort(),
    allowPython: options.allowPython,
    toolsets: options.toolsets,
    startHeadless: (headless) => startHeadlessSession(headless, log),
    ...(timeoutMs === undefined ? {} : { timeoutFor: () => timeoutMs }),
    log,
  });
  const shutdown = async (exitCode: number) => {
    await begun.stop().catch(() => undefined);
    process.exit(exitCode);
  };
  installProcessGuards(process, { shutdown, killChildren: killLiveSessions, log });
  process.stdin.on("close", () => void shutdown(0));
  process.on("SIGINT", () => void shutdown(0));
  process.on("SIGTERM", () => void shutdown(0));
  begun.ready.then(
    (started) => log(`blendworks: ready (${started.mode} mode, ${started.commands.length} commands)`),
    (error: unknown) => log(`blendworks: Blender did not start: ${error instanceof Error ? error.message : String(error)}; tool calls report this, and the server tries again on the next call`),
  );
  await begun.server.connect(new StdioServerTransport());
}

main().catch((error: unknown) => {
  console.error(`blendworks: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
