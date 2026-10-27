import { createServer } from "node:http";
import { existsSync, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { cacheRoot as scriptsCacheRoot } from "../../scripts/lib/paths.js";
import { toolsMain } from "../../scripts/lib/tools.js";
import { GLTFPACK_RELEASE, platformKey, type ReleasePin } from "../../src/package/gltfpack-release.js";
import { InstallError, cacheRoot, fetchWithLimit, installGltfpack, installedPath, lookupInstalled, sha256Of } from "../../src/package/native-install.js";
import { GLTFPACK_VARIABLE, selectNative } from "../../src/package/native.js";
import type { NativeResult, NativeRunner } from "../../src/package/native-run.js";
import { npmGltfpackVersion } from "../../src/package/tool.js";
import { zipOf } from "./zip-fixture.js";

const KEY = "linux-x64";
const EXECUTABLE = new TextEncoder().encode("#!/bin/sh\necho gltfpack 1.3\n");
const ARCHIVE = zipOf([{ name: "gltfpack", data: EXECUTABLE }]);

function pinFor(archive: Uint8Array, executable: Uint8Array = EXECUTABLE): ReleasePin {
  return {
    version: "1.3",
    baseUrl: "https://example.test/releases/v1.3/",
    platforms: { [KEY]: { archive: "gltfpack-ubuntu.zip", archiveBytes: archive.byteLength, archiveSha256: sha256Of(archive), executable: "gltfpack", executableSha256: sha256Of(executable) } },
  };
}

function scratch(): string {
  return mkdtempSync(join(tmpdir(), "blendworks-install-"));
}

function files(root: string): string[] {
  if (!existsSync(root)) return [];
  return readdirSync(root, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name);
}

function spyRunner(): { runner: NativeRunner; calls: () => number } {
  const run = vi.fn(async (): Promise<NativeResult> => {
    throw new Error("a binary was executed");
  });
  return { runner: run as unknown as NativeRunner, calls: () => run.mock.calls.length };
}

describe("the pinned release", () => {
  it("pins the version, the url and the sha256 of every platform archive and binary", () => {
    expect(Object.keys(GLTFPACK_RELEASE.platforms).sort()).toEqual(["darwin-arm64", "linux-x64", "win32-x64"]);
    expect(GLTFPACK_RELEASE.baseUrl).toBe(`https://github.com/zeux/meshoptimizer/releases/download/v${GLTFPACK_RELEASE.version}/`);
    for (const platform of Object.values(GLTFPACK_RELEASE.platforms)) {
      expect(platform.archiveSha256).toMatch(/^[0-9a-f]{64}$/);
      expect(platform.executableSha256).toMatch(/^[0-9a-f]{64}$/);
      expect(platform.archive).toMatch(/\.zip$/);
      expect(platform.archiveBytes).toBeGreaterThan(1_000_000);
    }
  });

  it("is the same gltfpack release as the npm build, so both produce the same meshopt output", () => {
    expect(npmGltfpackVersion().startsWith(`${GLTFPACK_RELEASE.version}.`)).toBe(true);
  });

  it("puts the cache where the scripts put it", () => {
    expect(cacheRoot({})).toBe(scriptsCacheRoot({}));
    const folder = scratch();
    expect(cacheRoot({ BLENDWORKS_CACHE: folder })).toBe(scriptsCacheRoot({ BLENDWORKS_CACHE: folder }));
    expect(cacheRoot({ BLENDWORKS_CACHE: "" })).toBe(scriptsCacheRoot({ BLENDWORKS_CACHE: "" }));
  });
});

describe("installing gltfpack", () => {
  it("downloads the pinned archive, verifies both hashes, and installs an executable once", async () => {
    const root = scratch();
    const pin = pinFor(ARCHIVE);
    const download = vi.fn(async () => ARCHIVE);
    const first = await installGltfpack({ root, pin, key: KEY, download });
    expect(first).toMatchObject({ status: "installed", version: "1.3", sha256: sha256Of(EXECUTABLE), path: installedPath(root, pin, KEY) });
    expect(download).toHaveBeenCalledWith("https://example.test/releases/v1.3/gltfpack-ubuntu.zip", ARCHIVE.byteLength);
    expect(readFileSync(first.path)).toEqual(Buffer.from(EXECUTABLE));
    if (process.platform !== "win32") expect(statSync(first.path).mode & 0o111).not.toBe(0);
    expect(files(root)).toEqual(["gltfpack"]);
    const second = await installGltfpack({ root, pin, key: KEY, download });
    expect(second.status).toBe("already installed");
    expect(download).toHaveBeenCalledTimes(1);
  });

  it("refuses a download whose hash is not the pinned one, keeps nothing, and executes nothing", async () => {
    const root = scratch();
    const pin = pinFor(ARCHIVE);
    const tampered = zipOf([{ name: "gltfpack", data: new TextEncoder().encode("#!/bin/sh\necho malware\n") }]);
    const error = await installGltfpack({ root, pin, key: KEY, download: async () => tampered }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(InstallError);
    expect((error as InstallError).code).toBe("hash");
    expect((error as InstallError).message).toContain(sha256Of(tampered));
    expect((error as InstallError).message).toContain(pin.platforms[KEY]!.archiveSha256);
    expect(files(root)).toEqual([]);
    const spy = spyRunner();
    const selection = await selectNative({ env: {}, root, pin, key: KEY, runner: spy.runner });
    expect(selection.tool).toBeNull();
    expect(spy.calls()).toBe(0);
  });

  it("refuses an archive whose binary is not the pinned one even when the archive hash matches", async () => {
    const root = scratch();
    const pin = pinFor(ARCHIVE, new TextEncoder().encode("a different binary"));
    await expect(installGltfpack({ root, pin, key: KEY, download: async () => ARCHIVE })).rejects.toThrow(/gltfpack in gltfpack-ubuntu.zip has sha256/);
    expect(files(root)).toEqual([]);
  });

  it("refuses an archive with the right hash that is not a zip file", async () => {
    const root = scratch();
    const garbage = new Uint8Array(2000).fill(7);
    const error = await installGltfpack({ root, pin: pinFor(garbage), key: KEY, download: async () => garbage }).catch((caught: unknown) => caught);
    expect((error as InstallError).code).toBe("archive");
    expect(files(root)).toEqual([]);
  });

  it("names the pinned platforms when this one has no release", async () => {
    const error = await installGltfpack({ root: scratch(), pin: pinFor(ARCHIVE), key: "freebsd-x64", download: async () => ARCHIVE }).catch((caught: unknown) => caught);
    expect((error as InstallError).code).toBe("unsupported");
    expect((error as InstallError).message).toContain("linux-x64");
    expect((error as InstallError).message).toContain(GLTFPACK_VARIABLE);
    expect(platformKey("win32", "x64")).toBe("win32-x64");
  });

  it("deletes an installed binary that no longer matches its pin and does not run it", async () => {
    const root = scratch();
    const pin = pinFor(ARCHIVE);
    const installed = await installGltfpack({ root, pin, key: KEY, download: async () => ARCHIVE });
    writeFileSync(installed.path, "tampered");
    const spy = spyRunner();
    const selection = await selectNative({ env: {}, root, pin, key: KEY, runner: spy.runner });
    expect(selection.tool).toBeNull();
    expect(selection.reason).toContain("is not the pinned one; it was deleted");
    expect(spy.calls()).toBe(0);
    expect(existsSync(installed.path)).toBe(false);
    expect(lookupInstalled(root, pin, KEY).state).toBe("missing");
  });

  it("replaces a tampered binary by installing again", async () => {
    const root = scratch();
    const pin = pinFor(ARCHIVE);
    const installed = await installGltfpack({ root, pin, key: KEY, download: async () => ARCHIVE });
    writeFileSync(installed.path, "tampered");
    const again = await installGltfpack({ root, pin, key: KEY, download: async () => ARCHIVE });
    expect(again.status).toBe("installed");
    expect(readFileSync(again.path)).toEqual(Buffer.from(EXECUTABLE));
  });
});

describe("downloading", () => {
  async function serve(handler: (path: string) => { status: number; body: Uint8Array }): Promise<{ url: string; close: () => void }> {
    const server = createServer((request, response) => {
      const { status, body } = handler(request.url ?? "");
      response.statusCode = status;
      response.end(body);
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    return { url: `http://127.0.0.1:${port}`, close: () => server.close() };
  }

  it("returns the bytes, and stops a download that grows past the pinned size", async () => {
    const server = await serve((path) => (path === "/big" ? { status: 200, body: new Uint8Array(5000) } : { status: 200, body: ARCHIVE }));
    try {
      expect(await fetchWithLimit(`${server.url}/ok`, 1_000_000)).toEqual(ARCHIVE);
      await expect(fetchWithLimit(`${server.url}/big`, 1000)).rejects.toThrow("larger than the pinned 1000 bytes");
    } finally {
      server.close();
    }
  });

  it("reports an error status and an unreachable server as download failures", async () => {
    const server = await serve(() => ({ status: 404, body: new Uint8Array(0) }));
    try {
      await expect(fetchWithLimit(`${server.url}/missing`, 1000)).rejects.toThrow("answered 404");
    } finally {
      server.close();
    }
    const error = await fetchWithLimit("http://127.0.0.1:1/none", 1000).catch((caught: unknown) => caught);
    expect((error as InstallError).code).toBe("download");
  });
});

describe("npm run tools:gltfpack", () => {
  it("refuses arguments with the usage", async () => {
    const errors: string[] = [];
    expect(await toolsMain(["--force"], { error: (line) => errors.push(line) })).toBe(2);
    expect(errors[0]).toContain("usage: npm run tools:gltfpack");
  });

  it("reports a hash mismatch, exits 1 and leaves the cache without a binary", async () => {
    const root = scratch();
    const errors: string[] = [];
    const pinned = GLTFPACK_RELEASE.platforms[platformKey()];
    const code = await toolsMain([], {
      env: { BLENDWORKS_CACHE: root },
      download: async () => new Uint8Array(pinned?.archiveBytes ?? 10).fill(1),
      error: (line) => errors.push(line),
      log: () => undefined,
    });
    expect(code).toBe(1);
    expect(errors.join("\n")).toMatch(/was not installed \((hash|unsupported)\)/);
    expect(files(root).filter((name) => name.startsWith("gltfpack"))).toEqual([]);
  });
});
