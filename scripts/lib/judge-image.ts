import { spawnSync, type SpawnSyncOptions } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, createReadStream, createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { parseArgs } from "node:util";
import { cacheRoot, ensureCacheRoot, repoRoot } from "./paths.js";

export const BLENDER_LINUX = {
  version: "5.2.3",
  file: "blender-5.2.3-linux-x64.tar.xz",
  url: "https://download.blender.org/release/Blender5.2/blender-5.2.3-linux-x64.tar.xz",
  sha256: "78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec",
  checksums: "https://download.blender.org/release/Blender5.2/blender-5.2.3.sha256",
} as const;

export const IMAGE_NAME = "blendworks-judge";
export const DOCKERFILE = join(repoRoot, "docker", "judge", "Dockerfile");
export const ENTRY_FILES = ["judge/isolation.js", "judge/path-policy.js", "judge/container/asset.js", "judge/container/cpus.js", "judge/container/entry.js", "judge/container/inputs.js", "judge/container/patch.js", "judge/container/probe.js", "judge/container/result.js"];

export const JUDGE_IMAGE_USAGE = `usage: npm run judge:image -- --commit <sha> [--name ${IMAGE_NAME}] [--no-cache]

Builds the judge image: Blender ${BLENDER_LINUX.version} for Linux (its sha256 checked against blender.org's
published checksum), Node and Blendworks at the commit with the dependencies of its lockfile, and the
asset and patch entry points of this checkout. Prints the image digest and the reference to pass to
intent-engine judge --sandbox-image. The same commit gives the same digest.`;

export type ImageRecord = { commit: string; name: string; tag: string; digest: string; image: string; entryCommit: string; entryClean: boolean; blenderSha256: string };

type Run = (command: string, args: string[], options?: SpawnSyncOptions) => { status: number | null; stdout: string; stderr: string };

export const runCommand: Run = (command, args, options = {}) => {
  const result = spawnSync(command, args, { encoding: "utf8", maxBuffer: 256 * 1024 * 1024, windowsHide: true, ...options });
  return { status: result.status, stdout: String(result.stdout ?? ""), stderr: String(result.stderr ?? "") };
};

export class ImageError extends Error {}

function must(run: Run, command: string, args: string[], options: SpawnSyncOptions = {}): string {
  const result = run(command, args, options);
  if (result.status !== 0) throw new ImageError(`${command} ${args.slice(0, 3).join(" ")} failed: ${(result.stderr || result.stdout).trim().slice(-800)}`);
  return result.stdout.trim();
}

export async function sha256File(path: string): Promise<string> {
  const hash = createHash("sha256");
  await pipeline(createReadStream(path), hash);
  return hash.digest("hex");
}

export async function ensureBlenderTarball(folder: string, fetcher: typeof fetch = fetch): Promise<string> {
  mkdirSync(folder, { recursive: true });
  const target = join(folder, BLENDER_LINUX.file);
  if (existsSync(target) && (await sha256File(target)) === BLENDER_LINUX.sha256) return target;
  rmSync(target, { force: true });
  const partial = `${target}.partial`;
  const response = await fetcher(BLENDER_LINUX.url);
  if (!response.ok || response.body === null) throw new ImageError(`could not download ${BLENDER_LINUX.url}: HTTP ${response.status}`);
  await pipeline(Readable.fromWeb(response.body as import("node:stream/web").ReadableStream), createWriteStream(partial));
  const found = await sha256File(partial);
  if (found !== BLENDER_LINUX.sha256) {
    rmSync(partial, { force: true });
    throw new ImageError(`the downloaded Blender has sha256 ${found}, not the published ${BLENDER_LINUX.sha256}`);
  }
  renameSync(partial, target);
  return target;
}

export function resolveCommit(commit: string, run: Run = runCommand): { sha: string; epoch: string } {
  const sha = must(run, "git", ["rev-parse", "--verify", `${commit}^{commit}`], { cwd: repoRoot });
  if (!/^[0-9a-f]{40}$/.test(sha)) throw new ImageError(`${commit} is not a commit`);
  return { sha, epoch: must(run, "git", ["show", "-s", "--format=%ct", sha], { cwd: repoRoot }) };
}

export function entryState(run: Run = runCommand): { commit: string; clean: boolean } {
  const commit = must(run, "git", ["rev-parse", "HEAD"], { cwd: repoRoot });
  const changed = must(run, "git", ["status", "--porcelain", "--", "src/judge/container", "src/judge/isolation.ts", "src/judge/path-policy.ts", "docker"], { cwd: repoRoot });
  return { commit, clean: changed === "" };
}

export function compileEntry(folder: string, run: Run = runCommand): void {
  rmSync(folder, { recursive: true, force: true });
  const windows = process.platform === "win32";
  must(run, windows ? "npx.cmd" : "npx", ["tsc", "-p", "tsconfig.build.json", "--outDir", folder], { cwd: repoRoot, shell: windows });
}

export function prepareContext(context: string, sha: string, run: Run = runCommand): void {
  rmSync(context, { recursive: true, force: true });
  mkdirSync(join(context, "entry"), { recursive: true });
  must(run, "git", ["archive", "--format=tar", "-o", join(context, "source.tar"), sha], { cwd: repoRoot });
  const compiled = `${context}-compiled`;
  compileEntry(compiled, run);
  for (const file of ENTRY_FILES) {
    const source = join(compiled, ...file.split("/"));
    if (!existsSync(source)) throw new ImageError(`the entry point ${file} did not compile`);
    mkdirSync(dirname(join(context, "entry", file)), { recursive: true });
    copyFileSync(source, join(context, "entry", file));
  }
  writeFileSync(join(context, "entry", "package.json"), '{ "type": "module" }\n');
  writeFileSync(join(context, "entry", "commit"), `${sha}\n`);
  rmSync(compiled, { recursive: true, force: true });
  copyFileSync(join(repoRoot, "docker", "judge", "blendworks-judge"), join(context, "blendworks-judge"));
}

export function stampContext(context: string, epoch: number): void {
  for (const file of contextFiles(context)) utimesSync(join(context, ...file.split("/")), epoch, epoch);
  const folders = (folder: string): string[] => readdirSync(folder, { withFileTypes: true }).flatMap((entry) => (entry.isDirectory() ? [...folders(join(folder, entry.name)), join(folder, entry.name)] : []));
  for (const folder of [...folders(context), context]) utimesSync(folder, epoch, epoch);
}

export function contextFiles(context: string): string[] {
  const found: string[] = [];
  const walk = (folder: string) => {
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(join(folder, entry.name));
      else found.push(relative(context, join(folder, entry.name)).split("\\").join("/"));
    }
  };
  walk(context);
  return found.sort();
}

export function buildArguments(options: { context: string; blenderFolder: string; sha: string; epoch: string; tag: string; metadata: string; noCache: boolean; extraCa?: string }): string[] {
  return [
    "buildx",
    "build",
    "--file",
    DOCKERFILE,
    "--build-context",
    `blender-download=${options.blenderFolder}`,
    "--build-arg",
    `SOURCE_DATE_EPOCH=${options.epoch}`,
    "--build-arg",
    `BLENDWORKS_COMMIT=${options.sha}`,
    "--provenance=false",
    "--sbom=false",
    "--platform",
    "linux/amd64",
    "--output",
    `type=image,name=${options.tag},rewrite-timestamp=true`,
    "--metadata-file",
    options.metadata,
    ...(options.noCache ? ["--no-cache"] : []),
    ...(options.extraCa === undefined ? [] : ["--secret", `id=extra-ca,src=${options.extraCa}`]),
    options.context,
  ];
}

export function digestFrom(metadata: string): string {
  const parsed = JSON.parse(readFileSync(metadata, "utf8")) as Record<string, unknown>;
  const digest = parsed["containerimage.digest"];
  if (typeof digest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(digest)) throw new ImageError(`docker reported no image digest in ${metadata}`);
  return digest;
}

export type BuildOptions = { commit: string; name?: string; noCache?: boolean; run?: Run; log?: (line: string) => void; fetcher?: typeof fetch };

export async function buildJudgeImage(options: BuildOptions): Promise<ImageRecord> {
  const run = options.run ?? runCommand;
  const log = options.log ?? ((line: string) => console.error(line));
  const name = options.name ?? IMAGE_NAME;
  const { sha, epoch } = resolveCommit(options.commit, run);
  const root = join(ensureCacheRoot(cacheRoot()), "judge-image");
  const blenderFolder = join(root, "blender");
  log(`Blender ${BLENDER_LINUX.version}: checking ${BLENDER_LINUX.file} against sha256 ${BLENDER_LINUX.sha256}`);
  await ensureBlenderTarball(blenderFolder, options.fetcher);
  const entry = entryState(run);
  if (!entry.clean) log("warning: the entry points or docker/ have uncommitted changes, so this image cannot be rebuilt from a commit");
  const context = join(root, "context", sha.slice(0, 12));
  prepareContext(context, sha, run);
  stampContext(context, Number(epoch));
  const tag = `${name}:${sha.slice(0, 12)}`;
  const metadata = join(root, `${sha.slice(0, 12)}.metadata.json`);
  log(`docker buildx build ${tag}${options.noCache === true ? " without cache" : ""}`);
  const extraCa = process.env["NODE_EXTRA_CA_CERTS"];
  const certificates = extraCa !== undefined && extraCa !== "" && existsSync(extraCa) ? { extraCa } : {};
  const built = run("docker", buildArguments({ context, blenderFolder, sha, epoch, tag, metadata, noCache: options.noCache === true, ...certificates }), { stdio: ["ignore", "inherit", "inherit"] });
  if (built.status !== 0) throw new ImageError(`docker buildx build failed with exit ${built.status}`);
  const digest = digestFrom(metadata);
  const record: ImageRecord = { commit: sha, name, tag, digest, image: `${name}@${digest}`, entryCommit: entry.commit, entryClean: entry.clean, blenderSha256: BLENDER_LINUX.sha256 };
  writeFileSync(join(root, `${sha.slice(0, 12)}.json`), `${JSON.stringify(record, null, 2)}\n`);
  return record;
}

export function imageRecord(commit: string, run: Run = runCommand): ImageRecord | null {
  const { sha } = resolveCommit(commit, run);
  try {
    return JSON.parse(readFileSync(join(cacheRoot(), "judge-image", `${sha.slice(0, 12)}.json`), "utf8")) as ImageRecord;
  } catch {
    return null;
  }
}

export async function judgeImageMain(argv: string[]): Promise<number> {
  let values;
  try {
    ({ values } = parseArgs({ args: argv, strict: true, options: { commit: { type: "string" }, name: { type: "string" }, "no-cache": { type: "boolean" }, help: { type: "boolean", short: "h" } } }));
  } catch (error) {
    console.error(`${(error as Error).message}\n\n${JUDGE_IMAGE_USAGE}`);
    return 2;
  }
  if (values.help === true || values.commit === undefined) {
    (values.help === true ? console.log : console.error)(JUDGE_IMAGE_USAGE);
    return values.help === true ? 0 : 2;
  }
  try {
    const record = await buildJudgeImage({ commit: values.commit, noCache: values["no-cache"] === true, ...(values.name === undefined ? {} : { name: values.name }) });
    console.log(`commit ${record.commit}`);
    console.log(`digest ${record.digest}`);
    console.log(`image ${record.image}`);
    return 0;
  } catch (error) {
    if (!(error instanceof ImageError)) throw error;
    console.error(error.message);
    return 1;
  }
}
