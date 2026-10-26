import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { DEFAULTS, judge } from "./run.js";

export const USAGE = `usage: blendworks judge <spec.json> <asset> [--out dir]
  [--timeout seconds] [--memory-mb n] [--max-triangles n] [--max-file-mb n]

Measures the asset in a sandboxed headless Blender 5.2, renders the spec's views,
writes report.json, summary.txt and contact-sheet.png to the out dir (default artifacts/judge),
and exits 0 only when every rule passes.`;

export class UsageError extends Error {}

function positive(text: string | undefined, name: string, fallback: number, unit: number): number {
  if (text === undefined) return fallback;
  if (!/^\d+$/.test(text) || Number(text) <= 0) throw new UsageError(`--${name} must be a positive whole number`);
  return Number(text) * unit;
}

export function parseCommand(argv: string[]) {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    strict: true,
    options: {
      out: { type: "string" },
      timeout: { type: "string" },
      "memory-mb": { type: "string" },
      "max-triangles": { type: "string" },
      "max-file-mb": { type: "string" },
      help: { type: "boolean", short: "h" },
    },
  });
  if (values.help) return { help: true as const };
  const [command, specPath, assetPath, ...extra] = positionals;
  if (command !== "judge" || specPath === undefined || assetPath === undefined || extra.length > 0) throw new UsageError(USAGE);
  const megabyte = 1024 * 1024;
  return {
    help: false as const,
    specPath,
    assetPath,
    outDir: values.out ?? "artifacts/judge",
    timeoutMs: positive(values.timeout, "timeout", DEFAULTS.timeoutMs, 1000),
    memoryBytes: positive(values["memory-mb"], "memory-mb", DEFAULTS.memoryBytes, megabyte),
    maxTriangles: positive(values["max-triangles"], "max-triangles", DEFAULTS.maxTriangles, 1),
    maxFileBytes: positive(values["max-file-mb"], "max-file-mb", DEFAULTS.maxFileBytes, megabyte),
  };
}

export async function main(argv: string[]): Promise<number> {
  let command: ReturnType<typeof parseCommand>;
  try {
    command = parseCommand(argv);
  } catch (error) {
    console.error(error instanceof UsageError ? error.message : `${(error as Error).message}\n\n${USAGE}`);
    return 2;
  }
  if (command.help) {
    console.log(USAGE);
    return 0;
  }
  const { help, ...options } = command;
  const report = await judge(options);
  console.log(report.summary);
  return report.passed ? 0 : 1;
}

function invokedDirectly(): boolean {
  const entry = process.argv[1];
  if (entry === undefined) return false;
  try {
    return realpathSync(entry) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

export function runCli(): void {
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (error: unknown) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = 1;
    },
  );
}

if (invokedDirectly()) runCli();
