import { createHash } from "node:crypto";
import { readFileSync, statSync } from "node:fs";
import { basename, posix } from "node:path";
import { parseArgs } from "node:util";
import { imageRecord, IMAGE_NAME, runCommand } from "./judge-image.js";

export const INTENT_ENGINE = "@intent-engine/cli@0.1.69";
export const SOLIVE_ROOT = "/judge";
export const SOLIVE_PIDS = 256;
export const SOLIVE_NOFILE = 1024;
export const SOLIVE_USER = "65534:65534";
export const DIGESTED = /^[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}$/;
export const RETRY_EXIT = 75;

export type JobKind = "asset" | "code";

export type Box = { memory: string; cpus: string; tmp: string };

export const BOX: Box = { memory: "8g", cpus: "4", tmp: "6g" };

export const JOB_DEFAULTS: Record<JobKind, { run: string; timeout: number }> = {
  asset: { run: "blendworks-judge asset", timeout: 3600 },
  code: { run: "blendworks-judge patch", timeout: 3600 },
};

export const JUDGE_COMMAND_USAGE = `usage: npm run judge:command -- <asset|code> --owner <address> --nonce <n> --spec <SPEC.md> --artifact <file or folder>
  [--commit <sha> | --image <name>@sha256:<64 hex>] [--keypair <judge key file>] [--verdict <file>]
  [--memory <n>m|<n>g] [--cpus <n>] [--tmp <n>m|<n>g] [--timeout <seconds>]

Prints, for ${INTENT_ENGINE}: the sandbox doctor command to run once per machine (it must print
"ready": true), the judge command without --yes to read the verdict first, the same command with
--yes that attests, and the docker run line Solive starts, to try an entry point by hand. The attestor
key stays with intent-engine on the host; the container gets only read-only copies of the artifact and
the spec, and /tmp (--sandbox-tmp) to write in. No GPU is passed: --sandbox-gpu is for a dedicated
judge machine only, and --sandbox none --i-trust-this-work never. --commit (default HEAD) takes the image npm run judge:image built for that commit.`;

export function quote(text: string): string {
  return /^[A-Za-z0-9_@%+=:,./-]+$/.test(text) ? text : `'${text.replaceAll("'", `'\\''`)}'`;
}

export type JudgeCommand = { kind: JobKind; owner: string; nonce: string; spec: string; artifact: string; image: string; keypair?: string; verdict?: string; box?: Partial<Box>; timeout?: number; yes?: boolean };

function digested(image: string): string {
  if (!DIGESTED.test(image)) throw new Error(`the image must be named by its digest as <name>@sha256:<64 hex>, not ${image}`);
  return image;
}

function boxArgs(image: string, box: Partial<Box> = {}): string[] {
  const chosen = { ...BOX, ...box };
  return ["--sandbox-image", digested(image), "--sandbox-memory", chosen.memory, "--sandbox-cpus", chosen.cpus, "--sandbox-tmp", chosen.tmp];
}

export function doctorArgs(image: string, keypair = "<judge.json>", box: Partial<Box> = {}): string[] {
  return ["npx", "-y", INTENT_ENGINE, "sandbox", "doctor", "--keypair", keypair, ...boxArgs(image, box)];
}

export function intentEngineArgs(command: JudgeCommand): string[] {
  const defaults = JOB_DEFAULTS[command.kind];
  return [
    "npx",
    "-y",
    INTENT_ENGINE,
    "judge",
    "--keypair",
    command.keypair ?? "<judge.json>",
    "--owner",
    command.owner,
    "--nonce",
    command.nonce,
    "--spec",
    command.spec,
    "--artifact",
    command.artifact,
    "--run",
    defaults.run,
    "--sandbox",
    "docker",
    ...boxArgs(command.image, command.box),
    "--timeout",
    String(command.timeout ?? defaults.timeout),
    "--verdict",
    command.verdict ?? "verdict.json",
    ...(command.yes === true ? ["--yes"] : []),
  ];
}

export type DryRun = { image: string; run: string; work: string; spec: string; artifact: string; artifactSha256: string; memory: string; cpus: string; tmp: string; name?: string; check?: string };

export function soliveDockerArgs(dry: DryRun): string[] {
  const mounts: [string, string][] = [
    [dry.work, "work"],
    [dry.spec, "spec"],
    ...(dry.check === undefined ? [] : [[dry.check, "check"] as [string, string]]),
  ];
  return [
    "run",
    ...(dry.name === undefined ? [] : ["--name", dry.name]),
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
    "--log-driver",
    "none",
    "--user",
    SOLIVE_USER,
    "--pids-limit",
    String(SOLIVE_PIDS),
    "--memory",
    dry.memory,
    "--memory-swap",
    dry.memory,
    "--cpus",
    dry.cpus,
    "--ulimit",
    `nofile=${SOLIVE_NOFILE}:${SOLIVE_NOFILE}`,
    "--ulimit",
    "core=0",
    "--tmpfs",
    `/tmp:rw,exec,nosuid,nodev,size=${dry.tmp}`,
    ...mounts.flatMap(([source, target]) => ["--mount", `type=bind,source=${source},target=${posix.join(SOLIVE_ROOT, target)},readonly`]),
    "--workdir",
    SOLIVE_ROOT,
    "--env",
    "HOME=/tmp",
    "--env",
    `SPEC_PATH=${posix.join(SOLIVE_ROOT, "spec", "SPEC.md")}`,
    "--env",
    `ARTIFACT_PATH=${dry.artifact}`,
    "--env",
    `ARTIFACT_SHA256=${dry.artifactSha256}`,
    "--entrypoint",
    "/bin/sh",
    dry.image,
    "-c",
    dry.run,
  ];
}

export function artifactSha256(path: string): string {
  return statSync(path).isFile() ? createHash("sha256").update(readFileSync(path)).digest("hex") : "<the manifest sha256 Solive computes for the folder>";
}

export function judgeCommandMain(argv: string[], log: (line: string) => void = console.log, fail: (line: string) => void = console.error): number {
  const [kind, ...rest] = argv;
  if (kind !== "asset" && kind !== "code") {
    fail(JUDGE_COMMAND_USAGE);
    return 2;
  }
  let values;
  try {
    ({ values } = parseArgs({
      args: rest,
      strict: true,
      options: { owner: { type: "string" }, nonce: { type: "string" }, spec: { type: "string" }, artifact: { type: "string" }, commit: { type: "string" }, image: { type: "string" }, keypair: { type: "string" }, verdict: { type: "string" }, memory: { type: "string" }, cpus: { type: "string" }, tmp: { type: "string" }, timeout: { type: "string" } },
    }));
  } catch (error) {
    fail(`${(error as Error).message}\n\n${JUDGE_COMMAND_USAGE}`);
    return 2;
  }
  if (values.owner === undefined || values.nonce === undefined || values.spec === undefined || values.artifact === undefined) {
    fail(JUDGE_COMMAND_USAGE);
    return 2;
  }
  const image = values.image ?? imageRecord(values.commit ?? "HEAD")?.image;
  if (image === undefined) {
    fail(`no judge image for ${values.commit ?? "HEAD"}: run npm run judge:image -- --commit ${values.commit ?? "HEAD"} first, or pass --image`);
    return 1;
  }
  if (values.image === undefined && runCommand("docker", ["image", "inspect", "--format", "{{.Id}}", image]).status !== 0) fail(`warning: docker does not know ${image} here; intent-engine will try to pull it`);
  const box: Partial<Box> = { ...(values.memory === undefined ? {} : { memory: values.memory }), ...(values.cpus === undefined ? {} : { cpus: values.cpus }), ...(values.tmp === undefined ? {} : { tmp: values.tmp }) };
  const command: JudgeCommand = {
    kind,
    owner: values.owner,
    nonce: values.nonce,
    spec: values.spec,
    artifact: values.artifact,
    image,
    box,
    ...(values.keypair === undefined ? {} : { keypair: values.keypair }),
    ...(values.verdict === undefined ? {} : { verdict: values.verdict }),
    ...(values.timeout === undefined ? {} : { timeout: Number(values.timeout) }),
  };
  let preview: string[];
  try {
    preview = intentEngineArgs(command);
  } catch (error) {
    fail((error as Error).message);
    return 2;
  }
  log('# once per machine; it must print "ready": true');
  log(doctorArgs(image, command.keypair, box).map(quote).join(" "));
  log("# read the verdict first");
  log(preview.map(quote).join(" "));
  log(`# attest; exit ${RETRY_EXIT} means try again later, never rejected`);
  log(intentEngineArgs({ ...command, yes: true }).map(quote).join(" "));
  const single = statSync(values.artifact).isFile();
  const dry = soliveDockerArgs({
    image,
    run: JOB_DEFAULTS[kind].run,
    work: "<copy>/work",
    spec: "<copy>/spec",
    artifact: single ? posix.join(SOLIVE_ROOT, "work", basename(values.artifact)) : posix.join(SOLIVE_ROOT, "work"),
    artifactSha256: artifactSha256(values.artifact),
    ...BOX,
    ...box,
  });
  log(`# Solive then starts: docker ${dry.map(quote).join(" ")}`);
  return 0;
}

export { IMAGE_NAME };
