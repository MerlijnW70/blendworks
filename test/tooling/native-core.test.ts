import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";
import { cargoArguments, libraryFile, NATIVE_DIR, nativeRequired, nativeVerdict, REQUIRED_MARKER, type NativeBuild } from "../../scripts/lib/native-build.js";
import { repoRoot } from "../../scripts/lib/paths.js";

function rustFiles(folder: string): string[] {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    return statSync(path).isDirectory() ? rustFiles(path) : path.endsWith(".rs") ? [path] : [];
  });
}

function withoutComments(text: string): string {
  return text.replace(/\/\/[^\n]*/g, "").replace(/"(?:\\.|[^"\\])*"/g, '""');
}

function build(partial: Partial<NativeBuild>): NativeBuild {
  return { ok: false, missingToolchain: false, library: "core.so", output: "out", ...partial };
}

function cargoAvailable(): boolean {
  return spawnSync(process.env["CARGO"] ?? "cargo", ["--version"], { encoding: "utf8" }).status === 0;
}

describe("the native terrain core", () => {
  it("is required where the image marker or BLENDWORKS_NATIVE=require says so", () => {
    expect(nativeRequired({}, () => false)).toBe(false);
    expect(nativeRequired({ BLENDWORKS_NATIVE: "require" }, () => false)).toBe(true);
    expect(nativeRequired({ BLENDWORKS_NATIVE: " Require " }, () => false)).toBe(true);
    expect(nativeRequired({}, (path) => path === REQUIRED_MARKER)).toBe(true);
  });

  it("falls back only when the toolchain is missing and the core is not required", () => {
    expect(nativeVerdict(build({ ok: true }), true).code).toBe(0);
    const fallback = nativeVerdict(build({ missingToolchain: true, output: "cannot run cargo" }), false);
    expect(fallback.code).toBe(0);
    expect(fallback.message).toContain("Python reference");
    expect(nativeVerdict(build({ missingToolchain: true }), true).code).toBe(1);
    expect(nativeVerdict(build({ output: "error[E0308]" }), false)).toEqual({ code: 1, message: "error[E0308]" });
  });

  it("builds offline from the lock file into native/target, the folder the loader reads", () => {
    const args = cargoArguments();
    for (const flag of ["--release", "--offline", "--locked"]) expect(args).toContain(flag);
    expect(args[args.indexOf("--target-dir") + 1]).toBe(join(NATIVE_DIR, "target"));
    expect(libraryFile("linux")).toBe("libblendworks_core.so");
    expect(libraryFile("win32")).toBe("blendworks_core.dll");
    const pkg = JSON.parse(readFileSync(join(repoRoot, "package.json"), "utf8")) as { scripts: Record<string, string> };
    expect(pkg.scripts["build"]).toMatch(/^tsx scripts\/build-native\.mjs && /);
  });

  it("has no dependencies and builds with Debian bookworm's rustc 1.63", () => {
    const manifest = readFileSync(join(NATIVE_DIR, "Cargo.toml"), "utf8");
    expect(manifest).toMatch(/^rust-version = "1\.63"$/m);
    expect(manifest.split("[dependencies]")[1]?.split("[")[0]?.trim()).toBe("");
    const lock = readFileSync(join(NATIVE_DIR, "Cargo.lock"), "utf8");
    expect(lock).toMatch(/^version = 3$/m);
    expect(lock.match(/\[\[package\]\]/g)).toHaveLength(1);
  });

  it("keeps unsafe code inside the FFI layer", () => {
    const source = join(NATIVE_DIR, "src");
    const lib = readFileSync(join(source, "lib.rs"), "utf8");
    expect(lib).toContain("#![deny(unsafe_code)]");
    expect(withoutComments(lib).match(/allow\(unsafe_code\)/g)).toHaveLength(1);
    expect(lib).toMatch(/#\[allow\(unsafe_code\)\]\s*pub mod ffi;/);
    const offenders = rustFiles(source)
      .map((path) => relative(source, path).split(sep).join("/"))
      .filter((path) => !path.startsWith("ffi/") && /\bunsafe\b/.test(withoutComments(readFileSync(join(source, path), "utf8"))));
    expect(offenders).toEqual([]);
  });

  it("is built and required in the judge image, with rustc 1.63 from the pinned snapshot", () => {
    const dockerfile = readFileSync(join(repoRoot, "docker", "judge", "Dockerfile"), "utf8");
    const runtime = dockerfile.split("FROM debian AS runtime")[1]?.split("FROM ")[0] ?? "";
    expect(runtime).toMatch(/apt-get install[^\n]* rustc cargo/);
    expect(runtime).toContain("rustc --version | grep -q '^rustc 1\\.63\\.'");
    expect(runtime).toContain(REQUIRED_MARKER);
    expect(dockerfile).toMatch(/snapshot\.debian\.org/);
  });

  it("documents every exported kernel and the measured speed table", () => {
    const doc = readFileSync(join(repoRoot, "docs", "terrain-core.md"), "utf8");
    const exported = [...readFileSync(join(NATIVE_DIR, "src", "ffi", "entries.rs"), "utf8").matchAll(/pub extern "C" fn (bw_\w+)/g)].map((match) => match[1]!);
    expect(exported.length).toBeGreaterThanOrEqual(9);
    for (const name of exported) expect(doc, name).toContain(name);
    for (const heading of ["## Build", "## Load", "## Add a kernel", "## Speed"]) expect(doc).toContain(heading);
    const table = doc.split("<!-- speed table -->")[1]?.split("<!-- end speed table -->")[0] ?? "";
    expect(table).toMatch(/\| stream-power step \|/);
    expect(table).toMatch(/\| lake routing \|/);
    expect(table).toMatch(/\| ADI diffusion \|/);
  });

  it("passes its Rust unit tests, panics at the boundary included", () => {
    if (!cargoAvailable()) {
      expect(nativeRequired()).toBe(false);
      console.log("skip: cargo is not installed here, so the Rust unit tests cannot run");
      return;
    }
    const run = spawnSync(process.env["CARGO"] ?? "cargo", ["test", "--offline", "--locked", "--manifest-path", join(NATIVE_DIR, "Cargo.toml"), "--target-dir", join(NATIVE_DIR, "target")], { cwd: repoRoot, encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
    const output = `${run.stdout}${run.stderr}`;
    expect(run.status, output.slice(-3000)).toBe(0);
    expect(output).toMatch(/a_panic_inside_a_kernel_becomes_an_error_code_and_message \.\.\. ok/);
    expect(output).toMatch(/a_panicking_thread_stops_its_team_instead_of_leaving_it_waiting \.\.\. ok/);
  }, 600_000);
});
