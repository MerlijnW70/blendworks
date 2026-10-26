import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { blenderPath } from "../blender.js";
import { measureOutputSchema, renderOutputSchema, type Measurements } from "./measurements.js";
import { summarize, type Failure, type Report } from "./report.js";
import { evaluateRules } from "./rules.js";
import { detectTools, planSandbox, runSandboxed, type Isolation, type Limits, type Tools } from "./sandbox.js";
import { DEFAULT_VIEWS, FORMATS, readSpec, SpecError, type AssetSpec } from "./spec.js";
import { blenderVersion, BlenderVersionError } from "./version.js";

export const SCRIPTS_DIR = fileURLToPath(new URL("../../bridge/judge/", import.meta.url));

export const DEFAULTS = { timeoutMs: 300_000, memoryBytes: 4096 * 1024 * 1024, maxTriangles: 2_000_000, maxFileBytes: 256 * 1024 * 1024 };

export type JudgeOptions = {
  specPath: string;
  assetPath: string;
  outDir: string;
  blender?: string;
  timeoutMs?: number;
  memoryBytes?: number;
  maxTriangles?: number;
  maxFileBytes?: number;
  tools?: Tools;
};

class StageFailure extends Error {
  constructor(readonly failure: Failure) {
    super(failure.message);
  }
}

const OUTPUTS = ["report.json", "summary.txt", "measurements.json", "render.json", "contact-sheet.png", "views"];

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function checkAsset(assetPath: string, maxFileBytes: number): number {
  if (!existsSync(assetPath)) throw new StageFailure({ stage: "asset", code: "missing", message: "the asset file does not exist" });
  const stats = statSync(assetPath);
  if (!stats.isFile()) throw new StageFailure({ stage: "asset", code: "not_a_file", message: "the asset path is not a file" });
  if (stats.size === 0) throw new StageFailure({ stage: "asset", code: "empty", message: "the asset file is empty" });
  if (stats.size > maxFileBytes) {
    throw new StageFailure({ stage: "asset", code: "too_large", message: `the asset is ${stats.size} bytes, over the judge's cap of ${maxFileBytes}` });
  }
  const extension = extname(assetPath).slice(1).toLowerCase();
  if (!(FORMATS as readonly string[]).includes(extension)) {
    throw new StageFailure({ stage: "asset", code: "unsupported_format", message: `.${extension} is not a supported format (${FORMATS.join(", ")})` });
  }
  return stats.size;
}

function readOutput(path: string): unknown {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return undefined;
  }
}

async function runScript(
  stage: "measure" | "render",
  blender: string,
  scriptArgs: string[],
  outputPath: string,
  limits: Limits,
  tools: Tools,
  workDir: string,
): Promise<{ output: unknown; isolation: Isolation }> {
  const plan = planSandbox(blender, join(SCRIPTS_DIR, `${stage}.py`), scriptArgs, limits, tools);
  const result = await runSandboxed(plan, workDir);
  if (result.timedOut) {
    throw new StageFailure({ stage, code: "timeout", message: `Blender took longer than ${limits.timeoutMs / 1000} s and was stopped` });
  }
  const output = readOutput(outputPath);
  if (output === undefined) {
    const tail = result.output.trim().split("\n").slice(-3).join(" | ").slice(0, 400);
    throw new StageFailure({
      stage,
      code: "crashed",
      message: `Blender exited with code ${result.code ?? result.signal} without a result (out of memory under the ${limits.memoryBytes / 1048576} MB cap, or a crash): ${tail}`,
    });
  }
  return { output, isolation: plan.isolation };
}

function prepareOutDir(outDir: string): void {
  mkdirSync(outDir, { recursive: true });
  for (const name of OUTPUTS) rmSync(join(outDir, name), { recursive: true, force: true });
}

export async function judge(options: JudgeOptions): Promise<Report> {
  const outDir = resolve(options.outDir);
  const specPath = resolve(options.specPath);
  const assetPath = resolve(options.assetPath);
  const limits: Limits = { timeoutMs: options.timeoutMs ?? DEFAULTS.timeoutMs, memoryBytes: options.memoryBytes ?? DEFAULTS.memoryBytes };
  const maxTriangles = options.maxTriangles ?? DEFAULTS.maxTriangles;
  prepareOutDir(outDir);
  const draft: Omit<Report, "summary"> = {
    passed: false,
    spec: { path: specPath, sha256: existsSync(specPath) && statSync(specPath).isFile() ? sha256(specPath) : null, name: null },
    asset: { path: assetPath, sha256: null, bytes: null },
    blender: null,
    sandbox: null,
    failure: null,
    rules: [],
    measurements: null,
    renders: null,
  };
  const workDir = mkdtempSync(join(tmpdir(), "blendworks-judge-"));
  try {
    let spec: AssetSpec;
    try {
      spec = readSpec(specPath);
    } catch (error) {
      if (error instanceof SpecError) throw new StageFailure({ stage: "spec", code: "invalid_spec", message: error.problems.join("; ") });
      throw error;
    }
    draft.spec.name = spec.name ?? null;
    draft.asset.bytes = checkAsset(assetPath, options.maxFileBytes ?? DEFAULTS.maxFileBytes);
    draft.asset.sha256 = sha256(assetPath);
    const blender = options.blender ?? blenderPath();
    try {
      draft.blender = await blenderVersion(blender);
    } catch (error) {
      if (error instanceof BlenderVersionError) throw new StageFailure({ stage: "blender", code: "unsupported_blender", message: error.message });
      throw error;
    }
    const tools = options.tools ?? detectTools();
    const measurementsPath = join(outDir, "measurements.json");
    const measured = await runScript("measure", blender, [assetPath, measurementsPath, "--max-triangles", String(maxTriangles)], measurementsPath, limits, tools, workDir);
    draft.sandbox = measured.isolation;
    const parsed = measureOutputSchema.safeParse(measured.output);
    if (!parsed.success) throw new StageFailure({ stage: "measure", code: "malformed", message: "the measuring script wrote malformed output" });
    if (!parsed.data.ok) throw new StageFailure({ stage: "measure", ...parsed.data.error });
    const measurements: Measurements = parsed.data.measurements;
    draft.measurements = measurements;
    draft.rules = evaluateRules(spec, measurements);
    const views = (spec.views ?? DEFAULT_VIEWS).join(",");
    const title = spec.name ?? basename(assetPath);
    const renderArgs = [assetPath, measurementsPath, outDir, "--views", views, "--title", title, "--max-triangles", String(maxTriangles)];
    const rendered = await runScript("render", blender, renderArgs, join(outDir, "render.json"), limits, tools, workDir);
    const renderParsed = renderOutputSchema.safeParse(rendered.output);
    if (!renderParsed.success) throw new StageFailure({ stage: "render", code: "malformed", message: "the render script wrote malformed output" });
    if (!renderParsed.data.ok) throw new StageFailure({ stage: "render", ...renderParsed.data.error });
    draft.renders = {
      views: renderParsed.data.views.map((entry) => ({ view: entry.view, path: resolve(entry.path) })),
      contactSheet: join(outDir, "contact-sheet.png"),
    };
  } catch (error) {
    if (!(error instanceof StageFailure)) throw error;
    draft.failure = error.failure;
  } finally {
    rmSync(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
  if (draft.failure) draft.rules.unshift({ rule: draft.failure.stage, measured: draft.failure.message, limit: "to complete", pass: false });
  draft.passed = draft.failure === null && draft.rules.length > 0 && draft.rules.every((rule) => rule.pass);
  const report: Report = { ...draft, summary: summarize(draft) };
  writeFileSync(join(outDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  writeFileSync(join(outDir, "summary.txt"), `${report.summary}\n`);
  return report;
}
