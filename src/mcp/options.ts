import { parseArgs } from "node:util";
import { DEFAULT_WORKSPACE } from "./workspace.js";

export interface ServerOptions {
  workspace: string;
  allowPython: boolean;
  timeoutMs: number | undefined;
  help: boolean;
}

export const USAGE = `Usage: node dist/mcp/index.js [--workspace <dir>] [--allow-python] [--timeout <seconds>]

The Blendworks MCP server, over stdio. It uses a desktop Blender add-on when one answers on
127.0.0.1:$BLENDWORKS_PORT (default 9876) within 1 s, and otherwise starts its own headless Blender ($BLENDER).

  --workspace <dir>      folder for every import, export and save (default ./workspace, created if missing)
  --allow-python         start the headless session with run_python, which runs arbitrary code
  --timeout <seconds>    default timeout for every request; without it each command has its own default,
                         listed by describe (120 s, 300 s for slow commands such as run_python and export)`;

export function parseOptions(argv: string[]): ServerOptions {
  const { values } = parseArgs({
    args: argv,
    options: {
      workspace: { type: "string" },
      "allow-python": { type: "boolean" },
      timeout: { type: "string" },
      help: { type: "boolean", short: "h" },
    },
    strict: true,
    allowPositionals: false,
  });
  let timeoutMs: number | undefined;
  if (values.timeout !== undefined) {
    const seconds = Number(values.timeout);
    if (!Number.isFinite(seconds) || seconds <= 0) throw new Error(`--timeout must be a positive number of seconds, not "${values.timeout}"`);
    timeoutMs = Math.round(seconds * 1000);
  }
  return {
    workspace: values.workspace ?? DEFAULT_WORKSPACE,
    allowPython: values["allow-python"] ?? false,
    timeoutMs,
    help: values.help ?? false,
  };
}
