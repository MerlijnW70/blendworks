import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { libraryFile, libraryPath, NATIVE_DIR } from "./native-build.js";
import { repoRoot } from "./paths.js";

export const DIST_DIR = join(NATIVE_DIR, "dist");
export const MANIFEST_FILE = "manifest.json";
export const RELEASE_VARIABLE = "BLENDWORKS_RELEASE";

export type Platform = { key: string; os: NodeJS.Platform; arch: string; target: string; runner: string; file: string };
export type ManifestEntry = { file: string; sha256: string; size: number };
export type Manifest = { schema: 1; commit: string; files: Record<string, ManifestEntry> };
export type DistReport = { ok: boolean; present: string[]; problems: string[] };

export const PLATFORMS: Platform[] = [
  { key: "win32-x64", os: "win32", arch: "x64", target: "x86_64-pc-windows-msvc", runner: "windows-2022", file: libraryFile("win32") },
  { key: "linux-x64", os: "linux", arch: "x64", target: "x86_64-unknown-linux-gnu", runner: "ubuntu-22.04", file: libraryFile("linux") },
  { key: "darwin-arm64", os: "darwin", arch: "arm64", target: "aarch64-apple-darwin", runner: "macos-14", file: libraryFile("darwin") },
  { key: "darwin-x64", os: "darwin", arch: "x64", target: "x86_64-apple-darwin", runner: "macos-13", file: libraryFile("darwin") },
];

export function platformKey(platform: NodeJS.Platform = process.platform, arch: string = process.arch): string | null {
  return PLATFORMS.find((entry) => entry.os === platform && entry.arch === arch)?.key ?? null;
}

export function releaseMode(env: NodeJS.ProcessEnv = process.env, flags: string[] = []): boolean {
  return flags.includes("--release") || (env[RELEASE_VARIABLE] ?? "").trim() === "1";
}

export function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function sourceCommit(env: NodeJS.ProcessEnv = process.env): string {
  const given = env["GITHUB_SHA"];
  if (given && /^[0-9a-f]{40}$/.test(given)) return given;
  const run = spawnSync("git", ["rev-parse", "HEAD"], { cwd: repoRoot, encoding: "utf8" });
  const commit = (run.stdout ?? "").trim();
  if (run.status !== 0 || !/^[0-9a-f]{40}$/.test(commit)) throw new Error("cannot read the source commit: run inside the git checkout or set GITHUB_SHA");
  return commit;
}

export function buildManifest(folder: string, commit: string): Manifest {
  const files: Record<string, ManifestEntry> = {};
  for (const platform of PLATFORMS) {
    const path = join(folder, platform.key, platform.file);
    if (existsSync(path)) files[platform.key] = { file: platform.file, sha256: sha256(path), size: readFileSync(path).length };
  }
  return { schema: 1, commit, files };
}

export function writeManifest(folder: string, commit: string): Manifest {
  const manifest = buildManifest(folder, commit);
  writeFileSync(join(folder, MANIFEST_FILE), `${JSON.stringify(manifest, null, 2)}\n`);
  return manifest;
}

export function readManifest(folder: string): Manifest | null {
  const path = join(folder, MANIFEST_FILE);
  if (!existsSync(path)) return null;
  const parsed = JSON.parse(readFileSync(path, "utf8")) as Manifest;
  return parsed.schema === 1 && typeof parsed.files === "object" && parsed.files !== null ? parsed : null;
}

export function checkDist(folder: string, release: boolean): DistReport {
  const manifest = readManifest(folder);
  const problems: string[] = [];
  const present: string[] = [];
  for (const platform of PLATFORMS) {
    const entry = manifest?.files[platform.key];
    const path = join(folder, platform.key, platform.file);
    if (!entry) {
      if (release) problems.push(`release build is missing the native core for ${platform.key} (${platform.target}): expected ${path} and a manifest entry`);
      continue;
    }
    if (!existsSync(path)) problems.push(`the manifest lists ${platform.key} but ${path} is missing`);
    else if (sha256(path) !== entry.sha256) problems.push(`${path} does not match the sha256 in the manifest`);
    else present.push(platform.key);
  }
  if (!manifest && !release) return { ok: true, present, problems: [] };
  if (!manifest) problems.unshift(`no ${MANIFEST_FILE} in ${folder}`);
  return { ok: problems.length === 0, present, problems };
}

export function copyCores(from: string, to: string): string[] {
  const copied: string[] = [];
  for (const platform of PLATFORMS) {
    const source = join(from, platform.key, platform.file);
    if (!existsSync(source)) continue;
    mkdirSync(join(to, platform.key), { recursive: true });
    copyFileSync(source, join(to, platform.key, platform.file));
    copied.push(platform.key);
  }
  return copied;
}

export function stageLocalBuild(to: string = DIST_DIR, platform: NodeJS.Platform = process.platform, arch: string = process.arch): string {
  const key = platformKey(platform, arch);
  if (key === null) throw new Error(`no prebuilt core exists for ${platform} ${arch}; supported are ${PLATFORMS.map((entry) => entry.key).join(", ")}`);
  const built = libraryPath(platform);
  if (!existsSync(built)) throw new Error(`${built} is missing; run npm run build:native first (needs Rust)`);
  mkdirSync(join(to, key), { recursive: true });
  copyFileSync(built, join(to, key, libraryFile(platform)));
  return key;
}

export function stageDist(from: string | null, to: string, release: boolean): DistReport {
  if (from !== null) copyCores(from, to);
  else stageLocalBuild(to);
  writeManifest(to, sourceCommit());
  return checkDist(to, release);
}
