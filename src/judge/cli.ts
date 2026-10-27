import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { CLOSEUP_DEFAULTS, closeups, closeupsSummary } from "./closeups.js";
import { DeviceError, deviceModeFromEnvironment, type DeviceMode } from "./device.js";
import { diffReports, diffText, readReport, ReportError } from "./diff.js";
import { DEFAULTS, judge } from "./run.js";
import { StageFailure } from "./stages.js";

const DEVICE_HELP = `Rendering uses BLENDWORKS_DEVICE: auto (default) tries OptiX, CUDA, HIP, Metal and oneAPI
inside the sandbox and falls back to the CPU; gpu fails with a reason when no GPU works; cpu never uses one.`;

export const JUDGE_USAGE = `usage: blendworks judge <spec.json> <asset> [--out dir] [--preview]
  [--timeout seconds] [--render-timeout seconds] [--memory-mb n] [--max-triangles n] [--max-file-mb n]

Measures the asset in a sandboxed headless Blender 5.2, renders the spec's views
(24 samples, denoised, fixed seed and resolution), writes report.json, summary.txt
and contact-sheet.png to the out dir (default artifacts/judge), and exits 0 only when every rule passes.
--preview measures and checks every rule and draws the UV layout, but renders no views.
The verdict depends on the measurements alone: a render that fails or times out is reported
and leaves the verdict as it is, unless the spec sets renders.required.
${DEVICE_HELP}`;

export const DIFF_USAGE = `usage: blendworks diff <reportA.json> <reportB.json> [--json]

Compares two judge reports: verdict, inputs, every rule, every measurement and the sha256 of
each rendered view, for revision rounds and disputes. Exits 0 when they match and 1 when they differ.`;

export const CLOSEUPS_USAGE = `usage: blendworks closeups <asset> --out <dir> [--res px] [--samples n]
  [--timeout seconds] [--memory-mb n] [--max-triangles n] [--max-file-mb n]

Renders 9 close-ups with the judge's light rig in the same sandbox: a hero three-quarter view,
plus a 2 x 2 grid of zoomed tiles from the front-right and from the back-left, each framed
to the asset's bounds, and writes them with a labelled closeup-sheet.png to the out dir.
Defaults: --res ${CLOSEUP_DEFAULTS.resolution} px, --samples ${CLOSEUP_DEFAULTS.samples} with denoising, --timeout ${CLOSEUP_DEFAULTS.timeoutMs / 1000} s.
${DEVICE_HELP}`;

export const USAGE = `${JUDGE_USAGE}\n\n${CLOSEUPS_USAGE}\n\n${DIFF_USAGE}`;

export class UsageError extends Error {}

const MEGABYTE = 1024 * 1024;

function positive(text: string | undefined, name: string, fallback: number, unit: number): number {
  if (text === undefined) return fallback;
  if (!/^\d+$/.test(text) || Number(text) <= 0) throw new UsageError(`--${name} must be a positive whole number`);
  return Number(text) * unit;
}

function deviceFromEnvironment(): DeviceMode {
  try {
    return deviceModeFromEnvironment();
  } catch (error) {
    if (error instanceof DeviceError) throw new UsageError(error.message);
    throw error;
  }
}

const SHARED_OPTIONS = {
  out: { type: "string" },
  timeout: { type: "string" },
  "memory-mb": { type: "string" },
  "max-triangles": { type: "string" },
  "max-file-mb": { type: "string" },
  help: { type: "boolean", short: "h" },
} as const;

function parseJudge(argv: string[]) {
  const { values, positionals } = parseArgs({ args: argv, allowPositionals: true, strict: true, options: { ...SHARED_OPTIONS, preview: { type: "boolean" }, "render-timeout": { type: "string" } } });
  if (values.help) return { help: JUDGE_USAGE };
  const [specPath, assetPath, ...extra] = positionals;
  if (specPath === undefined || assetPath === undefined || extra.length > 0) throw new UsageError(JUDGE_USAGE);
  return {
    command: "judge" as const,
    specPath,
    assetPath,
    outDir: values.out ?? "artifacts/judge",
    preview: values.preview === true,
    device: deviceFromEnvironment(),
    timeoutMs: positive(values.timeout, "timeout", DEFAULTS.timeoutMs, 1000),
    renderTimeoutMs: positive(values["render-timeout"], "render-timeout", positive(values.timeout, "timeout", DEFAULTS.timeoutMs, 1000), 1000),
    memoryBytes: positive(values["memory-mb"], "memory-mb", DEFAULTS.memoryBytes, MEGABYTE),
    maxTriangles: positive(values["max-triangles"], "max-triangles", DEFAULTS.maxTriangles, 1),
    maxFileBytes: positive(values["max-file-mb"], "max-file-mb", DEFAULTS.maxFileBytes, MEGABYTE),
  };
}

function parseDiff(argv: string[]) {
  const { values, positionals } = parseArgs({ args: argv, allowPositionals: true, strict: true, options: { json: { type: "boolean" }, help: { type: "boolean", short: "h" } } });
  if (values.help) return { help: DIFF_USAGE };
  const [before, after, ...extra] = positionals;
  if (before === undefined || after === undefined || extra.length > 0) throw new UsageError(DIFF_USAGE);
  return { command: "diff" as const, before, after, json: values.json === true };
}

function parseCloseups(argv: string[]) {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    strict: true,
    options: { ...SHARED_OPTIONS, res: { type: "string" }, samples: { type: "string" } },
  });
  if (values.help) return { help: CLOSEUPS_USAGE };
  const [assetPath, ...extra] = positionals;
  if (assetPath === undefined || values.out === undefined || extra.length > 0) throw new UsageError(CLOSEUPS_USAGE);
  const resolution = positive(values.res, "res", CLOSEUP_DEFAULTS.resolution, 1);
  const samples = positive(values.samples, "samples", CLOSEUP_DEFAULTS.samples, 1);
  if (resolution > CLOSEUP_DEFAULTS.maxResolution) throw new UsageError(`--res must be at most ${CLOSEUP_DEFAULTS.maxResolution}`);
  if (samples > CLOSEUP_DEFAULTS.maxSamples) throw new UsageError(`--samples must be at most ${CLOSEUP_DEFAULTS.maxSamples}`);
  return {
    command: "closeups" as const,
    assetPath,
    outDir: values.out,
    resolution,
    samples,
    device: deviceFromEnvironment(),
    timeoutMs: positive(values.timeout, "timeout", CLOSEUP_DEFAULTS.timeoutMs, 1000),
    memoryBytes: positive(values["memory-mb"], "memory-mb", DEFAULTS.memoryBytes, MEGABYTE),
    maxTriangles: positive(values["max-triangles"], "max-triangles", DEFAULTS.maxTriangles, 1),
    maxFileBytes: positive(values["max-file-mb"], "max-file-mb", DEFAULTS.maxFileBytes, MEGABYTE),
  };
}

export function parseCommand(argv: string[]) {
  const [command, ...rest] = argv;
  if (command === "judge") return parseJudge(rest);
  if (command === "closeups") return parseCloseups(rest);
  if (command === "diff") return parseDiff(rest);
  if (command === "--help" || command === "-h") return { help: USAGE };
  throw new UsageError(USAGE);
}

function runDiff(beforePath: string, afterPath: string, json: boolean): number {
  let before;
  let after;
  try {
    before = readReport(beforePath);
    after = readReport(afterPath);
  } catch (error) {
    if (!(error instanceof ReportError)) throw error;
    console.error(error.message);
    return 2;
  }
  const changes = diffReports(before, after);
  console.log(json ? JSON.stringify({ same: changes.length === 0, changes }, null, 2) : diffText(before, after, changes));
  return changes.length === 0 ? 0 : 1;
}

export async function main(argv: string[]): Promise<number> {
  let command: ReturnType<typeof parseCommand>;
  try {
    command = parseCommand(argv);
  } catch (error) {
    console.error(error instanceof UsageError ? error.message : `${(error as Error).message}\n\n${USAGE}`);
    return 2;
  }
  if ("help" in command) {
    console.log(command.help);
    return 0;
  }
  if (command.command === "diff") return runDiff(command.before, command.after, command.json);
  if (command.command === "judge") {
    const { command: _, ...options } = command;
    const report = await judge(options);
    console.log(report.summary);
    return report.passed ? 0 : 1;
  }
  const { command: _, ...options } = command;
  try {
    console.log(closeupsSummary(await closeups(options)));
    return 0;
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    console.error(`close-ups failed: ${error.failure.stage}: ${error.failure.message} [${error.failure.code}]`);
    return 1;
  }
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
