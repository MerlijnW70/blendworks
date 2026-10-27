import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { detectTools, LOW_INTEGRITY_SCRIPT, MOUNT_SCRIPT, NAMESPACE_FLAGS, planSandbox, runSandboxed, type Tools } from "../../src/judge/sandbox.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const LIMITS = { timeoutMs: 120_000, memoryBytes: 2048 * 1024 * 1024 };
const PROBE = resolve("test", "judge", "isolation_probe.py");
const VIEW = { workDir: "/work", writable: ["/work/out"], readOnly: ["/scripts", "/work/delivery"] };
const NAMESPACES: Tools = { platform: "linux", unshare: true, prlimit: true, mountNamespace: true };
const NO_NAMESPACES: Tools = { platform: "linux", unshare: true, prlimit: true, mountNamespace: false };
const LOW: Tools = { platform: "win32", unshare: false, prlimit: false, lowIntegrityPython: "C:/blender/5.2/python/bin/python.exe" };
const NO_LOW: Tools = { platform: "win32", unshare: false, prlimit: false, lowIntegrityPython: null };

describe("the isolation plan", () => {
  it("in Linux enters user, mount, PID and network namespaces and binds the system read-only and the work folder writable", () => {
    const plan = planSandbox("/opt/blender/blender", "measure.py", ["a.glb"], LIMITS, NAMESPACES, "cpu", VIEW);
    expect(plan.command).toBe("unshare");
    expect(plan.args.slice(0, NAMESPACE_FLAGS.length + 3)).toEqual([...NAMESPACE_FLAGS, "sh", MOUNT_SCRIPT, "/work/.sandbox-root"]);
    const rest = plan.args.slice(NAMESPACE_FLAGS.length + 3);
    const writable = rest.slice(0, rest.indexOf("--"));
    const readOnly = rest.slice(rest.indexOf("--") + 1, rest.indexOf("--", rest.indexOf("--") + 1));
    expect(writable).toEqual(["/work/out"]);
    expect(readOnly).toContain("/usr");
    expect(readOnly).toContain("/opt/blender");
    expect(readOnly.slice(-2)).toEqual(["/scripts", "/work/delivery"]);
    expect(readOnly).not.toContain("/home");
    expect(plan.isolation).toMatchObject({ network: "isolated", processes: "own PID namespace" });
    expect(plan.isolation.filesystem).toContain("read-only");
  });

  it("in Linux without a mount namespace falls back to the network namespace and says the files are not isolated", () => {
    const plan = planSandbox("blender", "measure.py", [], LIMITS, NO_NAMESPACES, "cpu", VIEW);
    expect(plan.args[0]).toBe("-rn");
    expect(plan.isolation.filesystem).toBe("not isolated (unshare cannot create a user and mount namespace here)");
    expect(plan.isolation.processes).toBe("shared PID namespace");
  });

  it("on Windows starts Blender through the low-integrity launcher, or says why not", () => {
    const plan = planSandbox("C:/blender/blender.exe", "measure.py", [], LIMITS, LOW, "cpu", VIEW);
    expect(plan.command).toBe(LOW.lowIntegrityPython);
    expect(plan.args.slice(0, 4)).toEqual(["-I", LOW_INTEGRITY_SCRIPT, "--", "C:/blender/blender.exe"]);
    expect(plan.lowIntegrity).toBe(true);
    expect(plan.isolation.filesystem).toBe("low integrity: writes only to the private work folder; reads are not limited");
    const fallback = planSandbox("C:/blender/blender.exe", "measure.py", [], LIMITS, NO_LOW, "cpu", VIEW);
    expect(fallback.command).toBe("C:/blender/blender.exe");
    expect(fallback.isolation.filesystem).toContain("not isolated (no low-integrity launcher");
  });
});

describe("the isolation on this machine", workBudget(180_000), () => {
  const tools = detectTools(blenderPath());
  const root = freshDir("isolation");
  const work = join(root, "work");
  const delivery = join(work, "delivery");
  const out = join(work, "out");
  const original = join(root, "original");
  const homeSecret = join(homedir(), `.blendworks-isolation-probe-${process.pid}`);
  for (const folder of [delivery, out, original]) mkdirSync(folder, { recursive: true });
  writeFileSync(join(delivery, "asset.glb"), "delivered");
  writeFileSync(join(original, "secret.txt"), "beside the original delivery");

  afterAll(() => rmSync(homeSecret, { force: true }));

  async function probe(reads: string[], writes: string[]) {
    const result = join(out, "probe.json");
    rmSync(result, { force: true });
    const view = { workDir: work, writable: [out], readOnly: [SCRIPTS_DIR, dirname(PROBE), delivery] };
    const plan = planSandbox(blenderPath(), PROBE, [result, ...reads, "--writes", ...writes], LIMITS, tools, "cpu", view);
    const run = await runSandboxed(plan, work);
    expect(existsSync(result), run.output.slice(-800)).toBe(true);
    return JSON.parse(readFileSync(result, "utf8")) as { read: Record<string, string>; write: Record<string, string>; processes: string[] };
  }

  it.runIf(tools.platform === "linux" && tools.mountNamespace === true)("in Linux lets a judged asset read only its own folder and write only the work folder", async () => {
    writeFileSync(homeSecret, "in the home folder");
    const outside = [join(original, "secret.txt"), homeSecret, ...["/mnt/c/Windows/win.ini", "/root/.bashrc"].filter((path) => existsSync(path))];
    const result = await probe([join(delivery, "asset.glb"), ...outside], [join(out, "written.txt"), join(delivery, "planted.txt"), join(original, "planted.txt"), "/usr/planted.txt"]);
    expect(result.read[join(delivery, "asset.glb")]).toBe("read");
    for (const path of outside) expect(result.read[path], path).toMatch(/^refused/);
    expect(result.write[join(out, "written.txt")]).toBe("written");
    for (const path of [join(delivery, "planted.txt"), join(original, "planted.txt"), "/usr/planted.txt"]) expect(result.write[path], path).toMatch(/^refused/);
    expect(existsSync(join(original, "planted.txt"))).toBe(false);
    expect(result.processes.length).toBeLessThan(4);
  });

  it.runIf(tools.platform === "win32" && typeof tools.lowIntegrityPython === "string")("on Windows lets a judged asset write only the work folder", async () => {
    const result = await probe([join(delivery, "asset.glb"), join(original, "secret.txt")], [join(out, "written.txt"), join(delivery, "planted.txt"), join(original, "planted.txt")]);
    expect(result.write[join(out, "written.txt")]).toBe("written");
    expect(result.write[join(delivery, "planted.txt")]).toMatch(/^refused/);
    expect(result.write[join(original, "planted.txt")]).toMatch(/^refused/);
    expect(existsSync(join(original, "planted.txt"))).toBe(false);
    expect(result.read[join(original, "secret.txt")]).toBe("read");
  });
});
