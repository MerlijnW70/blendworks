import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { desktopPort } from "./desktop.js";
import { startHeadlessSession } from "./headless.js";
import { parseOptions, USAGE } from "./options.js";
import { startBlendworks } from "./start.js";

async function main(): Promise<void> {
  const options = parseOptions(process.argv.slice(2));
  if (options.help) {
    console.error(USAGE);
    return;
  }
  const timeoutMs = options.timeoutMs;
  const log = (line: string) => console.error(line);
  const started = await startBlendworks({
    workspace: options.workspace,
    port: desktopPort(),
    allowPython: options.allowPython,
    toolsets: options.toolsets,
    startHeadless: (headless) => startHeadlessSession(headless, log),
    ...(timeoutMs === undefined ? {} : { timeoutFor: () => timeoutMs }),
    log,
  });
  const shutdown = async () => {
    await started.connection.close().catch(() => undefined);
    process.exit(0);
  };
  process.stdin.on("close", () => void shutdown());
  process.on("SIGINT", () => void shutdown());
  process.on("SIGTERM", () => void shutdown());
  await started.server.connect(new StdioServerTransport());
}

main().catch((error: unknown) => {
  console.error(`blendworks: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
