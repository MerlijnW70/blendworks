import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { buildNative, DEFAULT_SOURCE_DATE_EPOCH, libraryFile, linkerFlags, NATIVE_DIR, nativeEnvironment, nativeRequired, REMAPPED_NATIVE_DIR, RUSTFLAGS_SEPARATOR } from "../../scripts/lib/native-build.js";

const scratch = mkdtempSync(join(tmpdir(), "bw-native-repro-"));

afterAll(() => rmSync(scratch, { recursive: true, force: true }));

function cargoAvailable(): boolean {
  return spawnSync(process.env["CARGO"] ?? "cargo", ["--version"], { encoding: "utf8" }).status === 0;
}

function copySources(folder: string): string {
  const native = join(scratch, folder, "native");
  mkdirSync(native, { recursive: true });
  for (const part of ["Cargo.toml", "Cargo.lock", "src"]) cpSync(join(NATIVE_DIR, part), join(native, part), { recursive: true });
  return native;
}

function rustflags(env: NodeJS.ProcessEnv): string[] {
  return (env["CARGO_ENCODED_RUSTFLAGS"] ?? "").split(RUSTFLAGS_SEPARATOR);
}

function rlibOf(native: string): string {
  return join(native, "target", "release", "libblendworks_core.rlib");
}

describe("the native core builds deterministically", () => {
  it("remaps the source folder, fixes SOURCE_DATE_EPOCH, leaves out build ids and keeps no rustc info cache", () => {
    const linux = nativeEnvironment({ RUSTFLAGS: "-C target-cpu=native", CARGO_BUILD_RUSTFLAGS: "-g", PATH: "/bin" }, "/work/a/native", "x86_64-unknown-linux-gnu");
    expect(rustflags(linux)).toEqual([`--remap-path-prefix=/work/a/native=${REMAPPED_NATIVE_DIR}`, "-C", "link-arg=-Wl,--build-id=none"]);
    expect(linux["RUSTFLAGS"]).toBeUndefined();
    expect(linux["CARGO_BUILD_RUSTFLAGS"]).toBeUndefined();
    expect(linux["PATH"]).toBe("/bin");
    expect(linux["SOURCE_DATE_EPOCH"]).toBe(DEFAULT_SOURCE_DATE_EPOCH);
    expect(linux["CARGO_CACHE_RUSTC_INFO"]).toBe("0");
    expect(linux["CARGO_INCREMENTAL"]).toBe("0");
    expect(nativeEnvironment({ SOURCE_DATE_EPOCH: "1795842440" }, "/n", "x86_64-unknown-linux-gnu")["SOURCE_DATE_EPOCH"]).toBe("1795842440");
    expect(nativeEnvironment({ SOURCE_DATE_EPOCH: "soon" }, "/n", "x86_64-unknown-linux-gnu")["SOURCE_DATE_EPOCH"]).toBe(DEFAULT_SOURCE_DATE_EPOCH);
    expect(linkerFlags("x86_64-pc-windows-msvc")).toEqual(["-C", "link-arg=/Brepro"]);
    expect(linkerFlags("x86_64-pc-windows-gnu")).toEqual([]);
    expect(linkerFlags("aarch64-apple-darwin")).toEqual([]);
  });

  it("compiles in one codegen unit with fat LTO, so code order does not depend on thread timing", () => {
    const profile = readFileSync(join(NATIVE_DIR, "Cargo.toml"), "utf8").split("[profile.release]")[1] ?? "";
    expect(profile).toMatch(/^codegen-units = 1$/m);
    expect(profile).toMatch(/^lto = true$/m);
    expect(profile).toMatch(/^debug = false$/m);
    expect(profile).toMatch(/^incremental = false$/m);
  });

  it("gives byte-identical libraries from the same sources in two different folders", () => {
    if (!cargoAvailable()) {
      expect(nativeRequired()).toBe(false);
      console.log("skip: cargo is not installed here, so the native core cannot be built twice");
      return;
    }
    const first = copySources("a");
    const second = copySources(join("elsewhere", "deeper"));
    for (const native of [first, second]) {
      const built = buildNative(process.env, native);
      expect(built.ok, built.output.slice(-3000)).toBe(true);
      expect(existsSync(join(native, "target", ".rustc_info.json")), "cargo's rustc info cache lists its entries in hash order").toBe(false);
    }
    const library = (native: string) => readFileSync(join(native, "target", "release", libraryFile()));
    expect(library(first).equals(library(second)), "the cdylib differs between the two folders").toBe(true);
    expect(readFileSync(rlibOf(first)).equals(readFileSync(rlibOf(second))), "the rlib differs between the two folders").toBe(true);
    for (const native of [first, second]) {
      expect(library(native).includes(Buffer.from(native)), "the library holds its build folder").toBe(false);
      expect(readFileSync(rlibOf(native)).includes(Buffer.from(native)), "the rlib holds its build folder").toBe(false);
    }
    if (process.platform === "linux") expect(library(first).includes(Buffer.from(".note.gnu.build-id")), "the library has a build id").toBe(false);
  }, 900_000);
});
