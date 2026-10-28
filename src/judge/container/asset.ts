import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { pinned } from "./cpus.js";
import { assetSpecFrom, inputPath, mainAsset, type Layout } from "./inputs.js";
import { EntryError, result, type EntryResult } from "./result.js";

const JUDGE_EXIT: Record<number, "pass" | "fail" | "error"> = { 0: "pass", 1: "fail", 75: "error" };

type Report = { passed?: boolean; failure?: { stage: string; code: string; message: string } | null; rules?: { rule: string; pass: boolean }[]; asset?: { setSha256?: string | null }; spec?: { sha256?: string | null } };

function readReport(path: string): Report | null {
  try {
    return JSON.parse(readFileSync(path, "utf8")) as Report;
  } catch {
    return null;
  }
}

export const ASSET_LIMITS = { stage: 600, render: 900, total: 2400 };

export function assetLimits(env: NodeJS.ProcessEnv): typeof ASSET_LIMITS {
  const read = (name: string, fallback: number) => (/^\d+$/.test(env[name] ?? "") && Number(env[name]) > 0 ? Number(env[name]) : fallback);
  return { stage: read("BLENDWORKS_STAGE_SECONDS", ASSET_LIMITS.stage), render: read("BLENDWORKS_RENDER_SECONDS", ASSET_LIMITS.render), total: read("BLENDWORKS_ASSET_SECONDS", ASSET_LIMITS.total) };
}

export type AssetRequest = { layout: Layout; spec: string | undefined; artifact: string | undefined; commit: string | null; isolation: string; env: NodeJS.ProcessEnv };

export function judgeAsset(request: AssetRequest): EntryResult {
  const { layout } = request;
  const specPath = inputPath(layout.spec, request.spec, "spec");
  const artifact = inputPath(layout.work, request.artifact, "artifact");
  const asset = mainAsset(artifact, layout.work);
  const specText = readFileSync(specPath, "utf8");
  const assetSpec = assetSpecFrom(specText);
  const scratch = join(layout.scratch, "asset");
  const out = join(scratch, "out");
  for (const folder of [scratch, join(scratch, "tmp"), join(scratch, "cache"), join(scratch, "home")]) mkdirSync(folder, { recursive: true });
  const specJson = join(scratch, "spec.json");
  writeFileSync(specJson, `${JSON.stringify(assetSpec, null, 2)}\n`);
  const env = { ...request.env, BLENDER: layout.blender, TMPDIR: join(scratch, "tmp"), HOME: join(scratch, "home"), BLENDWORKS_CACHE: join(scratch, "cache") };
  const cli = join(layout.blendworks, "dist", "judge", "cli.js");
  const limits = assetLimits(request.env);
  const [command, args] = pinned(process.execPath, [cli, "judge", specJson, asset, "--out", out, "--timeout", String(limits.stage), "--render-timeout", String(limits.render)]);
  const run = spawnSync(command, args, { env, stdio: ["ignore", "inherit", "inherit"], timeout: limits.total * 1000, killSignal: "SIGKILL" });
  const stopped = run.signal !== null || (run.error as NodeJS.ErrnoException | undefined)?.code === "ETIMEDOUT";
  if (stopped) return result("asset", "error", `the judge ran past its ${limits.total} s limit and was stopped; that is a limit of this machine, not a verdict`, { commit: request.commit, isolation: request.isolation, details: { limits } });
  const verdict = run.status === null ? "error" : (JUDGE_EXIT[run.status] ?? "error");
  const report = readReport(join(out, "report.json"));
  const infrastructure = existsSync(join(out, "infrastructure.json")) ? readFileSync(join(out, "infrastructure.json"), "utf8") : null;
  const failed = (report?.rules ?? []).filter((rule) => !rule.pass).map((rule) => rule.rule);
  const reason =
    verdict === "pass"
      ? "every rule passes"
      : verdict === "fail"
        ? `failed: ${failed.join(", ") || report?.failure?.message || "see the report"}`
        : `the judge did not reach a verdict (exit ${run.status ?? run.signal}): ${infrastructure ?? "see its output"}`;
  if (verdict === "fail" && report === null) throw new EntryError("error", "the judge exited 1 without a report");
  return result("asset", verdict, reason, {
    commit: request.commit,
    isolation: request.isolation,
    inputs: {
      spec: relative(layout.root, specPath),
      specSha256: createHash("sha256").update(specText).digest("hex"),
      asset: relative(layout.root, asset),
      artifactSha256: request.env["ARTIFACT_SHA256"] ?? null,
    },
    details: { exit: run.status, setSha256: report?.asset?.setSha256 ?? null, failedRules: failed, failure: report?.failure ?? null, report: join(out, "report.json") },
  });
}
