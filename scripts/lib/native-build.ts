import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { repoRoot } from "./paths.js";

export const NATIVE_DIR = join(repoRoot, "native");
export const MINIMUM_RUST = "1.63";
export const REQUIRED_MARKER = "/etc/blendworks/native-required";
export const REQUIRE_VARIABLE = "BLENDWORKS_NATIVE";

export type NativeBuild = { ok: boolean; missingToolchain: boolean; library: string; output: string };

export function libraryFile(platform: NodeJS.Platform = process.platform): string {
  if (platform === "win32") return "blendworks_core.dll";
  if (platform === "darwin") return "libblendworks_core.dylib";
  return "libblendworks_core.so";
}

export function libraryPath(platform: NodeJS.Platform = process.platform): string {
  return join(NATIVE_DIR, "target", "release", libraryFile(platform));
}

export function nativeRequired(env: NodeJS.ProcessEnv = process.env, markerExists: (path: string) => boolean = existsSync): boolean {
  return (env[REQUIRE_VARIABLE] ?? "").trim().toLowerCase() === "require" || markerExists(REQUIRED_MARKER);
}

export function cargoArguments(): string[] {
  return ["build", "--release", "--offline", "--locked", "--manifest-path", join(NATIVE_DIR, "Cargo.toml"), "--target-dir", join(NATIVE_DIR, "target")];
}

export function buildNative(env: NodeJS.ProcessEnv = process.env): NativeBuild {
  const cargo = env["CARGO"] ?? "cargo";
  const run = spawnSync(cargo, cargoArguments(), { cwd: repoRoot, env, encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  const library = libraryPath();
  if (run.error) return { ok: false, missingToolchain: true, library, output: `cannot run ${cargo}: ${run.error.message}; install Rust ${MINIMUM_RUST} or newer (cargo and rustc) to build the native core` };
  const output = `${run.stdout ?? ""}${run.stderr ?? ""}`;
  if (run.status !== 0) return { ok: false, missingToolchain: false, library, output: `cargo build of the native core failed (exit ${run.status ?? "signal"}):\n${output.slice(-4000)}` };
  if (!existsSync(library)) return { ok: false, missingToolchain: false, library, output: `cargo build passed but ${library} is missing` };
  return { ok: true, missingToolchain: false, library, output };
}

export type NativeVerdict = { code: number; message: string };

export function nativeVerdict(built: NativeBuild, required: boolean): NativeVerdict {
  if (built.ok) return { code: 0, message: `native core built: ${built.library}` };
  if (built.missingToolchain && !required) return { code: 0, message: `native core not built, the bridge uses the Python reference kernels: ${built.output}` };
  return { code: 1, message: required && built.missingToolchain ? `the native core is required here: ${built.output}` : built.output };
}

export function buildNativeMain(env: NodeJS.ProcessEnv = process.env): number {
  const verdict = nativeVerdict(buildNative(env), nativeRequired(env));
  (verdict.code === 0 ? console.log : console.error)(verdict.message);
  return verdict.code;
}
