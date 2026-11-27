import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { checkReference } from "../path-policy.js";
import { pinned } from "./cpus.js";
import { inputPath, type Layout } from "./inputs.js";
import { EntryError, result, type EntryResult } from "./result.js";

const PATH_LINES = /^(?:diff --git (\S+|"(?:[^"\\]|\\.)*") (\S+|"(?:[^"\\]|\\.)*")|--- (.+)|\+\+\+ (.+)|rename from (.+)|rename to (.+)|copy from (.+)|copy to (.+))$/;
const LINK_MODES = /^(?:new file mode|new mode|old mode|deleted file mode|index [0-9a-f]+\.\.[0-9a-f]+) (120000|160000)$/;
const NOT_COPIED = new Set(["dist", ".cache", ".git"]);
const OUTPUT_TAIL = 60;
const GIT_IDENTITY = ["-c", "user.name=blendworks judge", "-c", "user.email=judge@blendworks.invalid", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"];

function unquote(text: string): string {
  if (!text.startsWith('"')) return text;
  const body = text.slice(1, -1);
  const bytes: number[] = [];
  const named: Record<string, number> = { n: 10, t: 9, r: 13, '"': 34, "\\": 92, a: 7, b: 8, f: 12, v: 11 };
  for (let index = 0; index < body.length; index += 1) {
    const char = body[index]!;
    if (char !== "\\") {
      bytes.push(...Buffer.from(char, "utf8"));
      continue;
    }
    const octal = /^[0-7]{3}/.exec(body.slice(index + 1));
    if (octal !== null) {
      bytes.push(parseInt(octal[0], 8));
      index += 3;
    } else {
      bytes.push(named[body[index + 1] ?? ""] ?? 0);
      index += 1;
    }
  }
  return Buffer.from(bytes).toString("utf8");
}

function stripPrefix(path: string): string | null {
  const plain = unquote(path.replace(/\t.*$/, "").trim());
  if (plain === "/dev/null") return null;
  return plain.replace(/^[ab]\//, "");
}

export function patchPaths(text: string): { paths: string[]; refused: string[] } {
  const paths = new Set<string>();
  const refused: string[] = [];
  const lines = text.split(/\r?\n/);
  const first = lines.findIndex((line) => line.startsWith("diff --git "));
  for (const line of lines.slice(first === -1 ? Math.max(0, lines.findIndex((entry) => entry.startsWith("--- "))) : first)) {
    if (LINK_MODES.test(line)) refused.push(`${line}: links and submodules are refused`);
    const match = PATH_LINES.exec(line);
    if (match === null) continue;
    for (const raw of match.slice(1)) {
      if (raw === undefined) continue;
      const path = stripPrefix(raw);
      if (path !== null) paths.add(path);
    }
  }
  for (const path of paths) {
    const verdict = checkReference(path, "path");
    if (!verdict.ok) refused.push(`${path.slice(0, 200)}: ${verdict.reason}`);
    else if (verdict.path.split("/")[0]!.toLowerCase() === ".git") refused.push(`${path.slice(0, 200)}: the patch may not touch .git`);
  }
  return { paths: [...paths].sort(), refused };
}

function patchFile(artifact: string, folder: string): string {
  if (statSync(artifact).isFile()) return artifact;
  const patches = readdirSync(artifact, { withFileTypes: true }).filter((entry) => entry.isFile() && /\.(patch|diff)$/i.test(entry.name));
  if (patches.length !== 1) throw new EntryError("fail", `the delivered folder must hold exactly one .patch file at its top, and holds ${patches.length}`);
  return inputPath(folder, join(artifact, patches[0]!.name), "patch");
}

function git(repo: string, args: string[], env: NodeJS.ProcessEnv): { ok: boolean; output: string } {
  const run = spawnSync("git", [...GIT_IDENTITY, ...args], { cwd: repo, env, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  return { ok: run.status === 0, output: `${run.stdout ?? ""}${run.stderr ?? ""}`.trim() };
}

function dependencies(repo: string): string {
  const lock = existsSync(join(repo, "package-lock.json")) ? readFileSync(join(repo, "package-lock.json")) : Buffer.alloc(0);
  const manifest = JSON.parse(readFileSync(join(repo, "package.json"), "utf8")) as Record<string, unknown>;
  const declared = JSON.stringify([manifest["dependencies"] ?? null, manifest["devDependencies"] ?? null, manifest["optionalDependencies"] ?? null]);
  return createHash("sha256").update(lock).update(declared).digest("hex");
}

export const CHECK_LIMITS = { total: 3000, quiet: 900 };

export function checkLimits(env: NodeJS.ProcessEnv): typeof CHECK_LIMITS {
  const read = (name: string, fallback: number) => (/^\d+$/.test(env[name] ?? "") && Number(env[name]) > 0 ? Number(env[name]) : fallback);
  return { total: read("BLENDWORKS_CHECK_SECONDS", CHECK_LIMITS.total), quiet: read("BLENDWORKS_QUIET_SECONDS", CHECK_LIMITS.quiet) };
}

type CheckRun = { code: number | null; stopped: string | null; tail: string[] };

export function runCheck(repo: string, env: NodeJS.ProcessEnv, limits: typeof CHECK_LIMITS, command: [string, string[]] = pinned("npm", ["run", "check"])): Promise<CheckRun> {
  return new Promise((resolve) => {
    const child = spawn(command[0], command[1], { cwd: repo, env, stdio: ["ignore", "pipe", "pipe"], detached: true });
    let lines: string[] = [];
    let stopped: string | null = null;
    const stop = (reason: string) => {
      if (stopped !== null) return;
      stopped = reason;
      try {
        process.kill(-child.pid!, "SIGKILL");
      } catch {
        child.kill("SIGKILL");
      }
    };
    const total = setTimeout(() => stop(`npm run check ran past its ${limits.total} s limit`), limits.total * 1000);
    let quiet = setTimeout(() => stop(`npm run check printed nothing for ${limits.quiet} s`), limits.quiet * 1000);
    const keep = (chunk: Buffer, to: NodeJS.WriteStream) => {
      to.write(chunk);
      lines = [...lines, ...chunk.toString("utf8").split("\n")].slice(-OUTPUT_TAIL);
      clearTimeout(quiet);
      quiet = setTimeout(() => stop(`npm run check printed nothing for ${limits.quiet} s`), limits.quiet * 1000);
    };
    child.stdout.on("data", (chunk: Buffer) => keep(chunk, process.stdout));
    child.stderr.on("data", (chunk: Buffer) => keep(chunk, process.stderr));
    const done = (code: number | null) => {
      clearTimeout(total);
      clearTimeout(quiet);
      resolve({ code, stopped, tail: lines.filter((line) => line.trim() !== "") });
    };
    child.on("error", () => done(null));
    child.on("close", (code) => done(code));
  });
}

export type PatchRequest = { layout: Layout; artifact: string | undefined; commit: string | null; isolation: string; env: NodeJS.ProcessEnv; jobs: string | undefined };

export async function judgePatch(request: PatchRequest): Promise<EntryResult> {
  const { layout } = request;
  const artifact = inputPath(layout.work, request.artifact, "artifact");
  const patch = patchFile(artifact, layout.work);
  const text = readFileSync(patch, "utf8");
  const inputs = { patch: relative(layout.root, patch), patchSha256: createHash("sha256").update(text).digest("hex"), artifactSha256: request.env["ARTIFACT_SHA256"] ?? null };
  const base = { commit: request.commit, isolation: request.isolation, inputs };
  const { paths, refused } = patchPaths(text);
  if (paths.length === 0) return result("patch", "fail", "the delivery is not a patch: it names no file", base);
  if (refused.length > 0) return result("patch", "fail", `the patch touches paths outside the repository: ${refused.slice(0, 10).join("; ")}`, { ...base, details: { refused } });
  const scratch = join(layout.scratch, "patch");
  const repo = join(scratch, "repo");
  rmSync(scratch, { recursive: true, force: true });
  for (const folder of [join(scratch, "tmp"), join(scratch, "home"), join(scratch, "npm")]) mkdirSync(folder, { recursive: true });
  cpSync(layout.blendworks, repo, { recursive: true, verbatimSymlinks: true, filter: (source) => !NOT_COPIED.has(relative(layout.blendworks, source)) });
  const env: NodeJS.ProcessEnv = {
    PATH: request.env["PATH"] ?? "/usr/local/bin:/usr/bin:/bin",
    LANG: "C.UTF-8",
    HOME: join(scratch, "home"),
    TMPDIR: join(scratch, "tmp"),
    BLENDER: layout.blender,
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
    npm_config_cache: join(scratch, "npm"),
    npm_config_update_notifier: "false",
    npm_config_fund: "false",
    npm_config_audit: "false",
    UV_THREADPOOL_SIZE: "2",
    GOMAXPROCS: "2",
    NODE_OPTIONS: "--v8-pool-size=2",
    ...(request.jobs === undefined ? {} : { BLENDWORKS_JOBS: request.jobs }),
  };
  for (const step of [["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "base"]]) {
    const done = git(repo, step, env);
    if (!done.ok) throw new EntryError("error", `could not set up the repository at the image's commit: ${done.output.slice(-400)}`);
  }
  const before = dependencies(repo);
  const applied = git(repo, ["apply", "--index", "--whitespace=nowarn", patch], env);
  if (!applied.ok) return result("patch", "fail", `the patch does not apply to ${request.commit ?? "the image's commit"}: ${applied.output.slice(-400)}`, { ...base, details: { paths } });
  const committed = git(repo, ["commit", "-q", "--allow-empty", "-m", "delivery"], env);
  if (!committed.ok) throw new EntryError("error", `could not commit the applied patch: ${committed.output.slice(-400)}`);
  if (dependencies(repo) !== before) {
    return result("patch", "error", "the patch changes the dependencies; the image holds those of its own commit and has no network to install others, so it was not judged", { ...base, details: { paths } });
  }
  const limits = checkLimits(request.env);
  const check = await runCheck(repo, env, limits);
  const passed = check.code === 0 && check.stopped === null;
  const reason = passed ? "npm run check passed with the patch applied" : (check.stopped ?? `npm run check failed (exit ${check.code ?? "signal"})`);
  return result("patch", passed ? "pass" : "fail", reason, { ...base, details: { paths, exit: check.code, limits, tail: check.tail } });
}
