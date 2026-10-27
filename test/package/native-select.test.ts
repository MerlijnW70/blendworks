import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import type { Tools } from "../../src/judge/sandbox.js";
import { compress } from "../../src/package/compress.js";
import { GltfpackError } from "../../src/package/gltfpack.js";
import type { ReleasePin } from "../../src/package/gltfpack-release.js";
import { installGltfpack, sha256Of } from "../../src/package/native-install.js";
import type { NativeRequest, NativeResult, NativeRunner } from "../../src/package/native-run.js";
import { GLTFPACK_VARIABLE, selectNative } from "../../src/package/native.js";
import { tinyTexturedGlb } from "../../src/package/tiny.js";
import { selectGltfpack } from "../../src/package/tool.js";
import { zipOf } from "./zip-fixture.js";

const KEY = "linux-x64";
const TOOLS: Tools = { platform: "linux", unshare: false, prlimit: false };
const LIMITS = { timeoutMs: 5000, memoryBytes: 512 * 1024 * 1024 };
const EXECUTABLE = new TextEncoder().encode("stand-in for the gltfpack binary");
const ARCHIVE = zipOf([{ name: "gltfpack", data: EXECUTABLE }]);
const PIN: ReleasePin = {
  version: "1.3",
  baseUrl: "https://example.test/",
  platforms: { [KEY]: { archive: "gltfpack.zip", archiveBytes: ARCHIVE.byteLength, archiveSha256: sha256Of(ARCHIVE), executable: "gltfpack", executableSha256: sha256Of(EXECUTABLE) } },
};

type Behaviour = { version?: string; versionCode?: number; probeCode?: number; probeLog?: string; throws?: string; result?: Partial<NativeResult> };

function result(overrides: Partial<NativeResult>): NativeResult {
  return { code: 0, signal: null, timedOut: false, log: "", output: null, isolation: { network: "isolated", memory: "m", timeoutMs: 1, platform: "linux", filesystem: "f", processes: "p" }, ...overrides };
}

function stub(behaviour: Behaviour = {}): { runner: NativeRunner; requests: NativeRequest[] } {
  const requests: NativeRequest[] = [];
  const runner: NativeRunner = async (request) => {
    requests.push(request);
    if (behaviour.throws !== undefined) throw new Error(behaviour.throws);
    if (request.args[0] === "-v") return result({ code: behaviour.versionCode ?? 0, log: `gltfpack ${behaviour.version ?? "1.3"}\n` });
    if (request.args.at(-1) === "-tc") return result({ code: behaviour.probeCode ?? 0, log: behaviour.probeLog ?? "", output: (behaviour.probeCode ?? 0) === 0 ? new Uint8Array([1]) : null });
    return result({ output: request.input?.data ?? null, ...behaviour.result });
  };
  return { runner, requests };
}

let root = "";

beforeEach(async () => {
  root = mkdtempSync(join(tmpdir(), "blendworks-select-"));
  await installGltfpack({ root, pin: PIN, key: KEY, download: async () => ARCHIVE });
});

function context(runner: NativeRunner, env: NodeJS.ProcessEnv = {}) {
  return { env, root, pin: PIN, key: KEY, tools: TOOLS, runner, limits: LIMITS };
}

describe("choosing the gltfpack that runs", () => {
  it("prefers the verified native binary that supports BasisU, and says so in its info", async () => {
    const { runner, requests } = stub();
    const tool = await selectGltfpack(context(runner));
    expect(tool.info).toMatchObject({ kind: "native", version: "1.3", source: "installed", sha256: sha256Of(EXECUTABLE), ktx2: true, ktx2Reason: null, meshopt: true, nativeSkipped: null });
    expect(tool.info.isolation).toMatchObject({ memory: expect.stringContaining("512 MB") });
    expect(requests.map((request) => request.args)).toEqual([["-v"], ["-i", "input.glb", "-o", "output.glb", "-tc"]]);
  });

  it("runs the native binary with arguments as an array, the input file, the limits and the sandbox tools", async () => {
    const { runner, requests } = stub();
    const tool = await selectGltfpack(context(runner));
    const input = new Uint8Array([9, 8, 7]);
    const packed = await tool.run(input, ["-kn", "-tq", "color", "8"]);
    expect(packed.output).toEqual(input);
    const last = requests.at(-1)!;
    expect(last).toMatchObject({ args: ["-i", "input.glb", "-o", "output.glb", "-kn", "-tq", "color", "8"], limits: LIMITS, tools: TOOLS, output: "output.glb" });
    expect(last.input).toEqual({ name: "input.glb", data: input });
  });

  it("falls back to the npm build, and says why, when no native binary is installed", async () => {
    const { runner, requests } = stub();
    const empty = mkdtempSync(join(tmpdir(), "blendworks-select-empty-"));
    const tool = await selectGltfpack({ ...context(runner), root: empty });
    expect(tool.info).toMatchObject({ kind: "npm", source: "npm package", sha256: null, ktx2: false, isolation: null });
    expect(tool.info.nativeSkipped).toContain("not installed (npm run tools:gltfpack installs it)");
    expect(tool.info.version).toMatch(/^1\.3\./);
    expect(requests).toEqual([]);
  });

  it("falls back to the npm build when the native binary was built without BasisU", async () => {
    const { runner } = stub({ probeCode: 1, probeLog: "Error: built without BasisU support\n" });
    const tool = await selectGltfpack(context(runner));
    expect(tool.info.kind).toBe("npm");
    expect(tool.info.nativeSkipped).toContain("was built without BasisU support (Error: built without BasisU support)");
  });

  it("refuses a native binary of another version", async () => {
    const { runner } = stub({ version: "1.2" });
    const selection = await selectNative(context(runner));
    expect(selection).toEqual({ tool: null, reason: expect.stringContaining("is gltfpack 1.2, but the judge is verified for gltfpack 1.3") });
  });

  it("refuses a binary that does not answer -v as gltfpack, or cannot start", async () => {
    expect((await selectNative(context(stub({ versionCode: 1 }).runner))).reason).toContain('did not answer "gltfpack 1.3"');
    expect((await selectNative(context(stub({ throws: "spawn failed" }).runner))).reason).toContain("could not be started: spawn failed");
  });

  it("asks a binary once for its version and capabilities, as long as it is unchanged", async () => {
    const { runner, requests } = stub();
    await selectGltfpack(context(runner));
    await selectGltfpack(context(runner));
    expect(requests).toHaveLength(2);
  });
});

describe("a binary named by BLENDWORKS_GLTFPACK", () => {
  function binary(): string {
    const path = join(mkdtempSync(join(tmpdir(), "blendworks-own-")), "gltfpack");
    writeFileSync(path, "my own build");
    return path;
  }

  it("is used instead of the installed one, and its version is checked too", async () => {
    const path = binary();
    const used = stub();
    const selection = await selectNative(context(used.runner, { [GLTFPACK_VARIABLE]: path }));
    expect(selection.tool).toMatchObject({ source: GLTFPACK_VARIABLE, path, version: "1.3" });
    expect(used.requests.every((request) => request.binary === path)).toBe(true);
    const refused = await selectNative(context(stub({ version: "1.4" }).runner, { [GLTFPACK_VARIABLE]: path }));
    expect(refused.reason).toContain("is gltfpack 1.4, but the judge is verified for gltfpack 1.3");
  });

  it("does not quietly switch to the installed binary when the named one is unusable", async () => {
    const spy = stub();
    const missing = join(tmpdir(), "blendworks-no-such-binary");
    expect((await selectNative(context(spy.runner, { [GLTFPACK_VARIABLE]: missing }))).reason).toContain("which does not exist");
    expect((await selectNative(context(spy.runner, { [GLTFPACK_VARIABLE]: tmpdir() }))).reason).toContain("which is not a file");
    const tool = await selectGltfpack(context(spy.runner, { [GLTFPACK_VARIABLE]: missing }));
    expect(tool.info.kind).toBe("npm");
    expect(spy.requests).toEqual([]);
  });

  it("ignores an empty value", async () => {
    expect((await selectNative(context(stub().runner, { [GLTFPACK_VARIABLE]: "" }))).tool?.source).toBe("installed");
  });
});

describe("running the native binary", () => {
  async function failing(overrides: Partial<NativeResult>) {
    const { runner } = stub({ result: overrides });
    const tool = await selectGltfpack(context(runner));
    return tool.run(new Uint8Array([1]), []).catch((caught: unknown) => caught);
  }

  it("turns a timeout, a kill, a failure and a missing output into gltfpack errors with the log", async () => {
    const timeout = await failing({ timedOut: true, code: null });
    expect(timeout).toBeInstanceOf(GltfpackError);
    expect(timeout).toMatchObject({ code: "timeout", message: "gltfpack took longer than 5 s and was stopped" });
    expect(await failing({ code: null, signal: "SIGKILL", log: "out of memory" })).toMatchObject({ code: "crashed", message: "gltfpack was stopped by SIGKILL: out of memory" });
    expect(await failing({ code: 3, log: "Error loading input.glb: bad\n" })).toMatchObject({ code: "failed", message: "Error loading input.glb: bad" });
    expect(await failing({ output: null })).toMatchObject({ code: "failed", message: "gltfpack wrote no output" });
  });
});

describe("compressing with the native binary", () => {
  it("asks for ETC1S colour maps and UASTC normal and data maps, with explicit qualities and threads", async () => {
    const { runner, requests } = stub();
    const result = await compress(tinyTexturedGlb(), { meshopt: true, ktx2: true, hasImages: true, select: context(runner) });
    expect(result.ktx2).toEqual({ requested: true, status: "written", reason: null });
    expect(result.gltfpack.kind).toBe("native");
    const args = requests.at(-1)!.args.slice(4);
    expect(args.slice(0, 4)).toEqual(["-kn", "-km", "-ke", "-cc"]);
    expect(args.slice(4, 6)).toEqual(["-tc", "-tu"]);
    expect(args[6]).toBe("normal,attrib");
    expect(args.slice(7, 16)).toEqual(["-tq", "color", "8", "-tq", "normal", "8", "-tq", "attrib", "8"]);
    expect(args[16]).toBe("-tj");
    expect(Number(args[17])).toBeGreaterThanOrEqual(1);
    expect(result.arguments).toEqual(args);
  });

  it("does not write KTX2 and says why when only the npm build is left", async () => {
    const empty = mkdtempSync(join(tmpdir(), "blendworks-select-empty-"));
    const result = await compress(tinyTexturedGlb(), { meshopt: true, ktx2: true, hasImages: true, select: { env: {}, root: empty, tools: TOOLS, runner: stub().runner } });
    expect(result.ktx2.status).toBe("unavailable");
    expect(result.ktx2.reason).toContain("gltfpack was built without BasisU support");
    expect(result.ktx2.reason).toContain("the native gltfpack is not installed (npm run tools:gltfpack installs it)");
    expect(result.ktx2.reason).toContain("the textures are copied unchanged");
    expect(result.gltfpack.kind).toBe("npm");
  });
});
