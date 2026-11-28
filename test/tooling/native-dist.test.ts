import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parseYaml, type Yaml } from "../../scripts/lib/mini-yaml.js";
import { buildManifest, checkDist, copyCores, PLATFORMS, platformKey, releaseMode, stageDist, writeManifest } from "../../scripts/lib/native-dist.js";
import { repoRoot } from "../../scripts/lib/paths.js";

const COMMIT = "a".repeat(40);

function artifacts(keys: string[]): string {
  const folder = mkdtempSync(join(tmpdir(), "native-dist-"));
  for (const platform of PLATFORMS.filter((entry) => keys.includes(entry.key))) {
    mkdirSync(join(folder, platform.key), { recursive: true });
    writeFileSync(join(folder, platform.key, platform.file), `core for ${platform.key}`);
  }
  return folder;
}

function asMap(value: Yaml | undefined): { [key: string]: Yaml } {
  expect(typeof value === "object" && !Array.isArray(value)).toBe(true);
  return value as { [key: string]: Yaml };
}

describe("prebuilt native cores", () => {
  it("name the core of each supported platform and architecture and nothing else", () => {
    expect(platformKey("win32", "x64")).toBe("win32-x64");
    expect(platformKey("linux", "x64")).toBe("linux-x64");
    expect(platformKey("darwin", "arm64")).toBe("darwin-arm64");
    expect(platformKey("darwin", "x64")).toBe("darwin-x64");
    expect(platformKey("linux", "arm64")).toBeNull();
    expect(platformKey("win32", "arm64")).toBeNull();
    expect(PLATFORMS.map((entry) => entry.file)).toEqual(["blendworks_core.dll", "libblendworks_core.so", "libblendworks_core.dylib", "libblendworks_core.dylib"]);
  });

  it("get a manifest with each file's sha256, size and the source commit", () => {
    const folder = artifacts(["win32-x64", "linux-x64"]);
    const manifest = writeManifest(folder, COMMIT);
    expect(manifest.commit).toBe(COMMIT);
    expect(Object.keys(manifest.files)).toEqual(["win32-x64", "linux-x64"]);
    expect(manifest.files["win32-x64"]).toEqual({ file: "blendworks_core.dll", sha256: createHash("sha256").update("core for win32-x64").digest("hex"), size: "core for win32-x64".length });
    expect(buildManifest(folder, COMMIT)).toEqual(JSON.parse(readFileSync(join(folder, "manifest.json"), "utf8")));
  });

  it("fail the packaging step in release mode when a platform is missing, and name it", () => {
    const folder = artifacts(["win32-x64", "linux-x64", "darwin-arm64"]);
    writeManifest(folder, COMMIT);
    const release = checkDist(folder, true);
    expect(release.ok).toBe(false);
    expect(release.problems.join("\n")).toContain("darwin-x64");
    expect(release.problems.join("\n")).not.toContain("linux-x64");
    expect(checkDist(folder, false).ok).toBe(true);
    const complete = artifacts(PLATFORMS.map((entry) => entry.key));
    writeManifest(complete, COMMIT);
    expect(checkDist(complete, true)).toMatchObject({ ok: true, present: PLATFORMS.map((entry) => entry.key) });
    expect(checkDist(artifacts([]), true).ok).toBe(false);
  });

  it("refuse a staged core whose bytes no longer match the manifest", () => {
    const folder = artifacts(["win32-x64"]);
    writeManifest(folder, COMMIT);
    writeFileSync(join(folder, "win32-x64", "blendworks_core.dll"), "swapped");
    const report = checkDist(folder, false);
    expect(report.ok).toBe(false);
    expect(report.problems[0]).toContain("does not match");
  });

  it("stage only the platforms that were built, with a manifest, when not in release mode", () => {
    const from = artifacts(["linux-x64"]);
    const to = mkdtempSync(join(tmpdir(), "native-stage-"));
    process.env["GITHUB_SHA"] = COMMIT;
    const report = stageDist(from, to, false);
    expect(report).toEqual({ ok: true, present: ["linux-x64"], problems: [] });
    expect(copyCores(from, mkdtempSync(join(tmpdir(), "native-copy-")))).toEqual(["linux-x64"]);
    expect(stageDist(from, mkdtempSync(join(tmpdir(), "native-rel-")), true).ok).toBe(false);
    delete process.env["GITHUB_SHA"];
  });

  it("enter release mode by flag or environment only", () => {
    expect(releaseMode({}, [])).toBe(false);
    expect(releaseMode({}, ["--release"])).toBe(true);
    expect(releaseMode({ BLENDWORKS_RELEASE: "1" }, [])).toBe(true);
    expect(releaseMode({ BLENDWORKS_RELEASE: "0" }, [])).toBe(false);
  });
});

describe("the native cores workflow", () => {
  const workflow = asMap(parseYaml(readFileSync(join(repoRoot, ".github", "workflows", "native-cores.yml"), "utf8")));
  const build = asMap(asMap(workflow["jobs"])["build"]);
  const include = (asMap(asMap(build["strategy"])["matrix"])["include"] ?? []) as Yaml[];

  it("parses and builds the four targets, one entry per platform", () => {
    expect(workflow["name"]).toBe("native-cores");
    expect(include.map((entry) => asMap(entry)["key"])).toEqual(PLATFORMS.map((entry) => entry.key));
    for (const platform of PLATFORMS) {
      const entry = asMap(include.find((item) => asMap(item)["key"] === platform.key));
      expect(entry["target"]).toBe(platform.target);
      expect(entry["runner"]).toBe(platform.runner);
      expect(entry["library"]).toBe(platform.file);
    }
  });

  it("builds offline and locked with a pinned toolchain, on glibc 2.31 for Linux", () => {
    const text = readFileSync(join(repoRoot, ".github", "workflows", "native-cores.yml"), "utf8");
    expect(text).toContain("--offline --locked");
    expect(text).toMatch(/RUST_VERSION: "\d+\.\d+\.\d+"/);
    expect(text).not.toMatch(/toolchain install (stable|nightly)/);
    expect(asMap(include.find((item) => asMap(item)["key"] === "linux-x64"))["container"]).toMatch(/^debian:bullseye/);
    expect(text).toContain("scripts/native-dist.mjs manifest cores --release");
  });

  it("produces one artifact per platform and a release-mode manifest", () => {
    const steps = (build["steps"] ?? []) as Yaml[];
    const upload = steps.map(asMap).find((step) => step["uses"] === "actions/upload-artifact@v4");
    expect(asMap(upload?.["with"])["name"]).toBe("core-${{ matrix.key }}");
    expect(Object.keys(asMap(asMap(workflow["jobs"])["manifest"]))).toContain("needs");
  });
});
