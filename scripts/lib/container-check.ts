import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { repoRoot } from "./paths.js";

export const IMAGE_VARIABLE = "BLENDWORKS_JUDGE_IMAGE";
export const COMMIT_LABEL = "org.blendworks.commit";
export const RESULT_PREFIX = "BLENDWORKS-RESULT ";
export const SANDBOX = { user: "65534:65534", pids: 256, files: 1024, memory: "8g", cpus: "4", tmp: "6g", root: "/judge" } as const;

export const CONTAINER_CHECK_USAGE = `usage: npx tsx scripts/check-container.mjs [--image <ref>] [--patch <file>] [--memory 8g] [--cpus 4] [--tmp 6g]

Runs npm run check inside the Blendworks judge image through its patch entry point, the way Solive's
docker sandbox judges a paid code job. Without --patch it checks the current commit: the patch is
git diff from the image's commit (its ${COMMIT_LABEL} label) to HEAD. With --patch it checks that
delivery. The image comes from --image or ${IMAGE_VARIABLE}. Exits 0 when the check passes.`;

export type Run = (command: string, args: string[]) => { status: number | null; stdout: string; stderr: string };

export const runCommand: Run = (command, args) => {
  const result = spawnSync(command, args, { cwd: repoRoot, encoding: "utf8", maxBuffer: 512 * 1024 * 1024, windowsHide: true });
  return { status: result.status, stdout: String(result.stdout ?? ""), stderr: String(result.stderr ?? "") };
};

export class ContainerCheckError extends Error {}

export type Box = { memory: string; cpus: string; tmp: string };

export type ContainerRun = { image: string; work: string; spec: string; patchName: string; patchSha256: string; box: Box; name: string };

export type ContainerResult = { verdict: "pass" | "fail" | "error"; exitCode: number; reason: string; commit: string | null; tail: string[] };

function must(run: Run, command: string, args: string[]): string {
  const result = run(command, args);
  if (result.status !== 0) throw new ContainerCheckError(`${command} ${args.slice(0, 2).join(" ")} failed: ${(result.stderr || result.stdout).trim().slice(-600)}`);
  return result.stdout;
}

export function imageCommit(image: string, run: Run = runCommand): string {
  const label = must(run, "docker", ["image", "inspect", "--format", `{{ index .Config.Labels "${COMMIT_LABEL}" }}`, image]).trim();
  if (!/^[0-9a-f]{40}$/.test(label)) throw new ContainerCheckError(`the image ${image} names no commit in its ${COMMIT_LABEL} label, so it is not a judge image`);
  return label;
}

export function patchOfHead(base: string, run: Run = runCommand): string {
  const head = must(run, "git", ["rev-parse", "HEAD"]).trim();
  if (head === base) throw new ContainerCheckError(`HEAD is the image's own commit ${base.slice(0, 12)}, so there is nothing to apply; build the image from main and check a branch, or pass --patch`);
  const known = run("git", ["cat-file", "-e", `${base}^{commit}`]);
  if (known.status !== 0) throw new ContainerCheckError(`the image's commit ${base.slice(0, 12)} is not in this repository; fetch it first`);
  const patch = must(run, "git", ["diff", "--binary", "--full-index", base, head]);
  if (patch.trim() === "") throw new ContainerCheckError(`HEAD has the same files as the image's commit ${base.slice(0, 12)}; there is nothing to check`);
  return patch;
}

export function dockerArguments(container: ContainerRun): string[] {
  const root = SANDBOX.root;
  return [
    "run",
    "--rm",
    "--name",
    container.name,
    "--network",
    "none",
    "--read-only",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
    "--ipc",
    "private",
    "--cgroupns",
    "private",
    "--user",
    SANDBOX.user,
    "--pids-limit",
    String(SANDBOX.pids),
    "--memory",
    container.box.memory,
    "--memory-swap",
    container.box.memory,
    "--cpus",
    container.box.cpus,
    "--ulimit",
    `nofile=${SANDBOX.files}:${SANDBOX.files}`,
    "--ulimit",
    "core=0",
    "--tmpfs",
    `/tmp:rw,exec,nosuid,nodev,size=${container.box.tmp}`,
    "--mount",
    `type=bind,source=${container.work},target=${root}/work,readonly`,
    "--mount",
    `type=bind,source=${container.spec},target=${root}/spec,readonly`,
    "--workdir",
    root,
    "--env",
    "HOME=/tmp",
    "--env",
    `SPEC_PATH=${root}/spec/SPEC.md`,
    "--env",
    `ARTIFACT_PATH=${root}/work/${container.patchName}`,
    "--env",
    `ARTIFACT_SHA256=${container.patchSha256}`,
    "--entrypoint",
    "/bin/sh",
    container.image,
    "-c",
    "blendworks-judge patch",
  ];
}

export function resultFrom(output: string, exitCode: number | null): ContainerResult {
  const line = output
    .split(/\r?\n/)
    .reverse()
    .find((entry) => entry.startsWith(RESULT_PREFIX));
  if (line === undefined) return { verdict: "error", exitCode: exitCode ?? 3, reason: `the container printed no ${RESULT_PREFIX.trim()} line (docker exit ${exitCode ?? "signal"})`, commit: null, tail: [] };
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(line.slice(RESULT_PREFIX.length)) as Record<string, unknown>;
  } catch {
    return { verdict: "error", exitCode: 3, reason: "the result line is not JSON", commit: null, tail: [] };
  }
  const verdict = parsed["verdict"] === "pass" || parsed["verdict"] === "fail" ? parsed["verdict"] : "error";
  const details = (parsed["details"] ?? {}) as { tail?: unknown };
  const tail = Array.isArray(details.tail) ? details.tail.filter((entry): entry is string => typeof entry === "string") : [];
  const passed = verdict === "pass" && exitCode === 0;
  return {
    verdict: passed ? "pass" : verdict === "pass" ? "error" : verdict,
    exitCode: passed ? 0 : verdict === "fail" ? 1 : 3,
    reason: passed || verdict !== "pass" ? String(parsed["reason"] ?? "") : `the result says pass but docker exited ${exitCode ?? "by signal"}`,
    commit: typeof parsed["commit"] === "string" ? parsed["commit"] : null,
    tail,
  };
}

function stream(args: string[]): Promise<{ code: number | null; output: string }> {
  return new Promise((done) => {
    const child = spawn("docker", args, { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    let output = "";
    const keep = (chunk: Buffer, to: NodeJS.WriteStream) => {
      to.write(chunk);
      output += chunk.toString("utf8");
    };
    child.stdout.on("data", (chunk: Buffer) => keep(chunk, process.stdout));
    child.stderr.on("data", (chunk: Buffer) => keep(chunk, process.stderr));
    child.on("error", (error) => done({ code: null, output: `${output}\n${error.message}` }));
    child.on("close", (code) => done({ code, output }));
  });
}

export function prepareInputs(patch: string, folder: string): { work: string; spec: string; patchName: string; patchSha256: string } {
  const work = join(folder, "work");
  const spec = join(folder, "spec");
  mkdirSync(work, { recursive: true });
  mkdirSync(spec, { recursive: true });
  writeFileSync(join(work, "delivery.patch"), patch);
  writeFileSync(join(spec, "SPEC.md"), "# Container check\n\nnpm run check passes with the patch applied.\n");
  return { work, spec, patchName: "delivery.patch", patchSha256: createHash("sha256").update(patch).digest("hex") };
}

export async function containerCheckMain(argv: string[], env: NodeJS.ProcessEnv = process.env): Promise<number> {
  let values;
  try {
    ({ values } = parseArgs({ args: argv, strict: true, options: { image: { type: "string" }, patch: { type: "string" }, memory: { type: "string" }, cpus: { type: "string" }, tmp: { type: "string" }, help: { type: "boolean", short: "h" } } }));
  } catch (error) {
    console.error(`${(error as Error).message}\n\n${CONTAINER_CHECK_USAGE}`);
    return 2;
  }
  if (values.help === true) {
    console.log(CONTAINER_CHECK_USAGE);
    return 0;
  }
  const image = values.image ?? env[IMAGE_VARIABLE];
  if (image === undefined || image === "") {
    console.error(`no image: pass --image or set ${IMAGE_VARIABLE}\n\n${CONTAINER_CHECK_USAGE}`);
    return 2;
  }
  const folder = mkdtempSync(join(tmpdir(), "blendworks-container-check-"));
  chmodSync(folder, 0o755);
  try {
    const base = imageCommit(image);
    const patch = values.patch === undefined ? patchOfHead(base) : readFileSync(resolve(values.patch), "utf8");
    const inputs = prepareInputs(patch, folder);
    const box = { memory: values.memory ?? SANDBOX.memory, cpus: values.cpus ?? SANDBOX.cpus, tmp: values.tmp ?? SANDBOX.tmp };
    console.error(`checking ${values.patch ?? `HEAD against ${base.slice(0, 12)}`} (patch sha256 ${inputs.patchSha256}) in ${image}`);
    const ran = await stream(dockerArguments({ image, ...inputs, box, name: `blendworks-check-${process.pid}` }));
    const outcome = resultFrom(ran.output, ran.code);
    console.log(`container check: ${outcome.verdict}: ${outcome.reason}`);
    return outcome.exitCode;
  } catch (error) {
    if (!(error instanceof ContainerCheckError)) throw error;
    console.error(error.message);
    return 3;
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
}
