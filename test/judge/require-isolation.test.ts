import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { main, parseCommand } from "../../src/judge/cli.js";
import { checkIsolation, containerShortfalls, InfrastructureError, probeContainer, type ContainerIsolation, type ProbeSources } from "../../src/judge/isolation.js";
import { INFRASTRUCTURE_FILE } from "../../src/judge/run.js";
import { detectTools, NAMESPACE_FLAGS, SANDBOX_REFUSED, sandboxRefusal, type Tools } from "../../src/judge/sandbox.js";
import { freshDir, makeFixtures, writeSpec } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const NAMESPACES: Tools = { platform: "linux", unshare: true, prlimit: true, mountNamespace: true };
const NETWORK_ONLY: Tools = { platform: "linux", unshare: true, prlimit: true, mountNamespace: false };
const NO_PRLIMIT: Tools = { platform: "linux", unshare: true, prlimit: false, mountNamespace: true };
const LOW_INTEGRITY: Tools = { platform: "win32", unshare: false, prlimit: false, lowIntegrityPython: "C:/blender/5.2/python/bin/python.exe" };
const NO_LAUNCHER: Tools = { platform: "win32", unshare: false, prlimit: false, lowIntegrityPython: null };
const SEALED: ContainerIsolation = { marker: "/.dockerenv", interfaces: [], rootReadOnly: true, memoryLimitBytes: 8 * 1024 ** 3, uid: 65534 };

const MOUNTINFO_READ_ONLY = "1 0 0:30 / / ro,relatime master:1 - overlay overlay ro,lowerdir=/x\n2 1 0:31 / /tmp rw,nosuid - tmpfs tmpfs rw\n";

function sources(files: Record<string, string>, folders: Record<string, string[]>, uid: number | null): ProbeSources {
  return { exists: (path) => path in files, read: (path) => files[path] ?? null, list: (path) => folders[path] ?? null, uid: () => uid };
}

let assets = "";
let work = "";

beforeAll(withWorkBudget(120_000, () => {
  ({ assets } = makeFixtures("require-isolation"));
  work = freshDir("require-isolation", "work");
}));

describe("--require-isolation", () => {
  it("is on by default for judge, and only --no-require-isolation turns it off", () => {
    expect(parseCommand(["judge", "spec.json", "a.glb"])).toMatchObject({ requireIsolation: true });
    expect(parseCommand(["judge", "spec.json", "a.glb", "--preview"])).toMatchObject({ requireIsolation: true, preview: true });
    expect(parseCommand(["judge", "spec.json", "a.glb", "--require-isolation"])).toMatchObject({ requireIsolation: true });
    expect(parseCommand(["judge", "spec.json", "a.glb", "--no-require-isolation"])).toMatchObject({ requireIsolation: false });
  });

  it("names every missing layer on the host: no namespaces, no memory cap, the Windows low-integrity mode", () => {
    expect(checkIsolation(NAMESPACES, null).shortfalls).toEqual([]);
    expect(checkIsolation(NETWORK_ONLY, null).shortfalls.join(" ")).toContain("the host's files are not isolated");
    expect(checkIsolation(NO_PRLIMIT, null).shortfalls.join(" ")).toContain("no memory cap");
    expect(checkIsolation(LOW_INTEGRITY, null).shortfalls.join(" ")).toContain("low-integrity mode, which limits only writes");
    expect(checkIsolation(NO_LAUNCHER, null).shortfalls).toHaveLength(1);
    expect(checkIsolation({ ...NAMESPACES, platform: "darwin" }, null).shortfalls.join(" ")).toContain("no sandbox on darwin");
  });

  it("accepts a sealed container and names what an open one lacks", () => {
    expect(checkIsolation(NETWORK_ONLY, SEALED).shortfalls).toEqual([]);
    expect(containerShortfalls({ ...SEALED, interfaces: ["eth0"] })).toEqual(["the container has a network (eth0); run it with --network none"]);
    expect(containerShortfalls({ ...SEALED, rootReadOnly: false })).toHaveLength(1);
    expect(containerShortfalls({ ...SEALED, memoryLimitBytes: null })).toHaveLength(1);
    expect(containerShortfalls({ ...SEALED, uid: 0 })).toHaveLength(1);
    const open = checkIsolation(NETWORK_ONLY, { ...SEALED, interfaces: ["eth0"], memoryLimitBytes: null });
    expect(open.shortfalls.slice(0, 2)).toEqual(["the container has a network (eth0); run it with --network none", "the container has no memory limit; run it with --memory"]);
    expect(checkIsolation(NAMESPACES, { ...SEALED, interfaces: ["eth0"] }).shortfalls).toEqual([]);
  });

  it("probes the container from the files the kernel shows it", () => {
    const files = { "/.dockerenv": "", "/proc/self/mountinfo": MOUNTINFO_READ_ONLY, "/sys/fs/cgroup/memory.max": "8589934592\n" };
    expect(probeContainer("linux", sources(files, { "/sys/class/net": ["lo"] }, 65534))).toEqual(SEALED);
    expect(probeContainer("linux", sources({ ...files, "/sys/fs/cgroup/memory.max": "max\n" }, { "/sys/class/net": ["lo", "eth0"] }, 0))).toMatchObject({ interfaces: ["eth0"], memoryLimitBytes: null, uid: 0 });
    expect(probeContainer("linux", sources({ ...files, "/proc/self/mountinfo": MOUNTINFO_READ_ONLY.replace(" ro,relatime", " rw,relatime") }, {}, 1000))).toMatchObject({ rootReadOnly: false, interfaces: ["unknown"] });
    expect(probeContainer("linux", sources({}, {}, 1000))).toBeNull();
    expect(probeContainer("win32", sources(files, {}, null))).toBeNull();
  });

  it("turns a sandbox that cannot confirm its read-only mounts into an infrastructure error, not a verdict", () => {
    const plan = { command: "unshare", args: [...NAMESPACE_FLAGS, "sh", "sandbox.sh"] };
    const refusal = sandboxRefusal(plan, { code: SANDBOX_REFUSED, output: "blendworks-sandbox: /work/with space/delivery is not read-only in the sandbox: writable: /x\n" });
    expect(refusal).toBeInstanceOf(InfrastructureError);
    expect(refusal?.message).toContain("/work/with space/delivery is not read-only");
    expect(sandboxRefusal(plan, { code: 1, output: "blendworks-sandbox: x" })).toBeNull();
    expect(sandboxRefusal({ command: "blender", args: [] }, { code: SANDBOX_REFUSED, output: "blendworks-sandbox: x" })).toBeNull();
  });
});

describe("the judge command on this machine", workBudget(180_000), () => {
  const check = checkIsolation(detectTools(), probeContainer());

  it.runIf(check.shortfalls.length > 0)("refuses with exit 75 (try again later) and infrastructure.json, writes no report and starts no Blender", async () => {
    const out = freshDir("require-isolation", "refused");
    const spec = writeSpec(work, "refused", { views: ["front"] });
    expect(await main(["judge", spec, join(assets, "crate.glb"), "--preview", "--out", out])).toBe(75);
    expect(existsSync(join(out, "report.json"))).toBe(false);
    expect(JSON.parse(readFileSync(join(out, INFRASTRUCTURE_FILE), "utf8"))).toMatchObject({ verdict: null, infrastructure: true, code: "isolation" });
    expect(await main(["judge", spec, join(assets, "crate.glb"), "--preview", "--no-require-isolation", "--out", out])).toBe(0);
    expect(existsSync(join(out, INFRASTRUCTURE_FILE))).toBe(false);
  });

  it.runIf(check.shortfalls.length === 0)("judges with isolation required, and names the container when it runs in one", async () => {
    const out = freshDir("require-isolation", "isolated");
    const spec = writeSpec(work, "isolated", { views: ["front"] });
    expect(await main(["judge", spec, join(assets, "crate.glb"), "--preview", "--out", out])).toBe(0);
    const report = JSON.parse(readFileSync(join(out, "report.json"), "utf8"));
    if (check.container !== null) expect(report.summary).toContain("isolation: container");
  });
});
