import { createHash } from "node:crypto";
import { existsSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, sep } from "node:path";
import type { Failure } from "./report.js";
import { planSandbox, runSandboxed, type Isolation, type SandboxDevice } from "./sandbox.js";
import { readShared } from "./shared-access.js";
import { SCRIPTS_DIR, workOut, type Sandbox } from "./stages.js";

export const PASS_SCRIPT = "judge.py";
export const PASS_STAGES = ["measure", "reference", "views", "sheet", "closeups"] as const;
export type PassStage = (typeof PASS_STAGES)[number];
export type StageGroup = Extract<Failure["stage"], "measure" | "reference" | "render" | "closeups">;

export const STAGE_GROUP: Record<PassStage, StageGroup> = { measure: "measure", reference: "reference", views: "render", sheet: "render", closeups: "closeups" };
export const PASS_OUTPUTS: Record<PassStage, string> = {
  measure: "measurements.json",
  reference: "silhouettes.json",
  views: "render.json",
  sheet: "sheet.json",
  closeups: join("closeups", "closeups.json"),
};

const PROGRESS = "progress.log";
const LOW_INTEGRITY_LAUNCH_FAILED = 120;
const WATCH_INTERVAL_MS = 20;
const BLENDER_EXIT_LINES = [/^$/, /^Blender quit$/, /^Blender \d+\.\d+(\.\d+)? .*\(hash [0-9a-f]+/];

export type PassRequest = {
  asset: string;
  stages: PassStage[];
  args: string[];
  device: SandboxDevice;
  sandbox: Sandbox;
  budgets: Record<StageGroup, number>;
  addressSpaceUntilGpu?: boolean;
  signal?: AbortSignal;
  script?: string;
};

export type StageRecord = { stage: PassStage; ok: boolean; seconds: number; endedAt: number; digest: string | null };

export const VERIFIED_STAGES: readonly PassStage[] = ["measure", "reference"];

export type PassResult = {
  isolation: Isolation;
  spawnedAt: number;
  records: StageRecord[];
  interrupted: { stage: PassStage; failure: Failure } | null;
  aborted: boolean;
};

type ProgressEvent = { event: "start" | "end" | "failed" | "finish"; stage: PassStage | null; at: number; seconds: number | null; digest?: string | null };

export function readProgress(path: string): ProgressEvent[] {
  let text: string;
  try {
    text = readShared(path).toString("utf8");
  } catch {
    return [];
  }
  const events: ProgressEvent[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line.endsWith("}")) continue;
    try {
      events.push(JSON.parse(line) as ProgressEvent);
    } catch {
      continue;
    }
  }
  return events;
}

export function passOutput(sandbox: Sandbox, stage: PassStage): unknown {
  try {
    return JSON.parse(readShared(join(workOut(sandbox), PASS_OUTPUTS[stage])).toString("utf8"));
  } catch {
    return undefined;
  }
}

export function clearPassOutputs(sandbox: Sandbox, stages: readonly PassStage[]): void {
  rmSync(join(workOut(sandbox), PROGRESS), { force: true });
  for (const stage of stages) rmSync(join(workOut(sandbox), PASS_OUTPUTS[stage]), { force: true });
}

function stageFiles(out: string, stage: PassStage): string[] {
  const files = [PASS_OUTPUTS[stage]];
  const folder = join(out, "silhouettes");
  if (stage === "reference" && existsSync(folder)) files.push(...readdirSync(folder).sort().map((name) => join("silhouettes", name)));
  return files;
}

export function stageDigest(out: string, stage: PassStage): string | null {
  const digest = createHash("sha256");
  for (const name of stageFiles(out, stage)) {
    let data: Buffer;
    try {
      data = readShared(join(out, name));
    } catch {
      return null;
    }
    digest.update(Buffer.from(`${name.split(sep).join("/")}|`, "utf8"));
    digest.update(createHash("sha256").update(data).digest());
  }
  return digest.digest("hex");
}

export function changedStage(out: string, records: StageRecord[]): { stage: PassStage; failure: Failure } | null {
  for (const record of records) {
    if (!VERIFIED_STAGES.includes(record.stage) || stageDigest(out, record.stage) === record.digest) continue;
    const group = STAGE_GROUP[record.stage];
    return { stage: record.stage, failure: { stage: group, code: "changed", message: `the ${record.stage} output changed after its stage ended` } };
  }
  return null;
}

class StageClock {
  private readonly started = new Map<StageGroup, number>();
  private seen = 0;
  current: PassStage;
  finished = false;

  constructor(
    private readonly path: string,
    private readonly stages: PassStage[],
  ) {
    this.current = stages[0]!;
  }

  begin(at: number): void {
    this.started.set(STAGE_GROUP[this.current], at);
  }

  update(now: number): void {
    const events = readProgress(this.path);
    for (const event of events.slice(this.seen)) {
      if (event.event === "finish") this.finished = true;
      if (event.stage === null) continue;
      if (event.event === "start") {
        this.current = event.stage;
        if (!this.started.has(STAGE_GROUP[event.stage])) this.started.set(STAGE_GROUP[event.stage], now);
      } else {
        const next = this.stages[this.stages.indexOf(event.stage) + 1];
        if (next !== undefined) this.current = next;
      }
    }
    this.seen = events.length;
  }

  elapsed(now: number): number {
    return now - (this.started.get(STAGE_GROUP[this.current]) ?? now);
  }
}

function interruption(request: PassRequest, records: StageRecord[], timedOut: boolean, clock: StageClock, code: number | null, signal: string | null, output: string, lowIntegrity: boolean, started: boolean): { stage: PassStage; failure: Failure } {
  const done = new Set(records.map((record) => record.stage));
  const stage = timedOut ? clock.current : (request.stages.find((entry) => !done.has(entry)) ?? request.stages[request.stages.length - 1]!);
  const group = STAGE_GROUP[stage];
  if (timedOut) return { stage, failure: { stage: group, code: "timeout", message: `Blender took longer than ${request.budgets[group] / 1000} s and was stopped` } };
  if (!started && code === LOW_INTEGRITY_LAUNCH_FAILED && lowIntegrity) {
    return { stage, failure: { stage: group, code: "sandbox", message: `the low-integrity launcher could not start Blender: ${output.trim().slice(-300)}` } };
  }
  const tail = output.trim().split("\n").filter((line) => !BLENDER_EXIT_LINES.some((pattern) => pattern.test(line.trim()))).slice(-3).join(" | ").slice(0, 400);
  const memoryMb = request.sandbox.limits.memoryBytes / 1048576;
  return { stage, failure: { stage: group, code: "crashed", message: `Blender exited with code ${code ?? signal} without a result (out of memory under the ${memoryMb} MB cap, or a crash): ${tail}` } };
}

export async function runPass(request: PassRequest): Promise<PassResult> {
  const { sandbox } = request;
  const out = workOut(sandbox);
  clearPassOutputs(sandbox, request.stages);
  const progressPath = join(out, PROGRESS);
  const args = [request.asset, out, "--stages", request.stages.join(","), ...request.args];
  const script = request.script ?? join(SCRIPTS_DIR, PASS_SCRIPT);
  const view = { workDir: sandbox.workDir, writable: [out], readOnly: [...new Set([SCRIPTS_DIR, dirname(script), sandbox.delivery])] };
  const plan = planSandbox(sandbox.blender, script, args, sandbox.limits, sandbox.tools, request.device, view, { addressSpaceUntilGpu: request.addressSpaceUntilGpu === true });
  let spawnedAt = Date.now();
  const clock = new StageClock(progressPath, request.stages);
  const started = () => {
    spawnedAt = Date.now();
    clock.begin(spawnedAt);
  };
  let aborted = false;
  const check = (): "running" | "finished" | "expired" => {
    if (request.signal?.aborted) {
      aborted = true;
      return "finished";
    }
    const now = Date.now();
    clock.update(now);
    if (clock.finished) return "finished";
    return clock.elapsed(now) > request.budgets[STAGE_GROUP[clock.current]] ? "expired" : "running";
  };
  const result = await runSandboxed(plan, sandbox.workDir, { intervalMs: WATCH_INTERVAL_MS, started, check });
  clock.update(Date.now());
  const events = readProgress(progressPath);
  const records: StageRecord[] = events.flatMap((event) =>
    event.stage !== null && (event.event === "end" || event.event === "failed") ? [{ stage: event.stage, ok: event.event === "end", seconds: event.seconds ?? 0, endedAt: event.at * 1000, digest: event.digest ?? null }] : [],
  );
  const changed = changedStage(out, records);
  const finished = events.some((event) => event.event === "finish") && !result.timedOut;
  const interrupted =
    changed ?? (finished || aborted ? null : interruption(request, records, result.timedOut, clock, result.code, result.signal, result.output, plan.lowIntegrity, existsSync(progressPath)));
  return { isolation: plan.isolation, spawnedAt, records, interrupted, aborted };
}
