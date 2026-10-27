import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { blenderPath, blenderThreadArguments } from "../../src/blender.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { BLENDER_FLAGS, detectTools, planSandbox, runSandboxed, sandboxEnvironment, type SandboxDevice, type Tools } from "../../src/judge/sandbox.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";

useBlenderSlot();

const LIMITS = { timeoutMs: 60_000, memoryBytes: 2048 * 1024 * 1024 };
const WINDOWS: Tools = { platform: "win32", unshare: false, prlimit: false };
const LINUX: Tools = { platform: "linux", unshare: true, prlimit: true };
const BARE_LINUX: Tools = { platform: "linux", unshare: false, prlimit: false };
const PROBE = resolve("test", "judge", "sandbox_probe.py");

describe("the sandbox plan", () => {
  it("always starts Blender headless, from factory settings, with auto-run off and the thread cap, and passes the memory cap to the script", () => {
    for (const tools of [WINDOWS, LINUX, BARE_LINUX]) {
      const plan = planSandbox("blender", "measure.py", ["asset.glb", "out.json"], LIMITS, tools);
      const blenderAt = plan.args.indexOf("blender");
      const blenderArgs = blenderAt === -1 ? plan.args : plan.args.slice(blenderAt + 1);
      expect(blenderArgs.slice(0, BLENDER_FLAGS.length)).toEqual([...BLENDER_FLAGS]);
      expect(blenderArgs).toContain("--disable-autoexec");
      expect(blenderArgs).not.toContain("--enable-autoexec");
      expect(blenderArgs.slice(BLENDER_FLAGS.length)).toEqual([...blenderThreadArguments(), "--python", "measure.py", "--", "asset.glb", "out.json", "--memory-mb", "2048"]);
    }
  });

  it("on Windows runs Blender directly under a job object", () => {
    const plan = planSandbox("blender.exe", "measure.py", [], LIMITS, WINDOWS);
    expect(plan.command).toBe("blender.exe");
    expect(plan.isolation).toMatchObject({ network: "not isolated", platform: "windows", timeoutMs: 60_000 });
    expect(plan.isolation.memory).toContain("job object");
  });

  it("on Linux cuts the network with unshare -rn and caps the address space with prlimit", () => {
    const plan = planSandbox("blender", "measure.py", [], LIMITS, LINUX);
    expect(plan.command).toBe("unshare");
    expect(plan.args.slice(0, 6)).toEqual(["-rn", "prlimit", `--as=${LIMITS.memoryBytes}`, "--core=0", "--", "blender"]);
    expect(plan.isolation.network).toBe("isolated");
  });

  it("for a GPU render on Linux keeps unshare -rn and swaps the address-space cap for a data-segment cap", () => {
    const plan = planSandbox("blender", "render.py", ["a.glb"], LIMITS, LINUX, "gpu");
    expect(plan.command).toBe("unshare");
    expect(plan.args.slice(0, 6)).toEqual(["-rn", "prlimit", `--data=${LIMITS.memoryBytes}`, "--core=0", "--", "blender"]);
    expect(plan.args).not.toContain(`--as=${LIMITS.memoryBytes}`);
    expect(plan.args.slice(-4)).toEqual(["--memory-mb", "2048", "--memory-kind", "data"]);
    expect(plan.isolation).toMatchObject({ network: "isolated", memory: "prlimit data segment, 2048 MB", timeoutMs: 60_000 });
    expect(plan.gpu).toBe(true);
  });

  it("for a CPU render keeps the address-space cap and hides the GPUs", () => {
    const plan = planSandbox("blender", "render.py", [], LIMITS, LINUX, "cpu");
    expect(plan.isolation.memory).toBe("prlimit address space, 2048 MB");
    expect(plan.gpu).toBe(false);
    expect(plan.args).not.toContain("--memory-kind");
    const home = freshDir("sandbox", "environment");
    expect(sandboxEnvironment(home, false)).toMatchObject({ CUDA_VISIBLE_DEVICES: "", HIP_VISIBLE_DEVICES: "" });
    expect(sandboxEnvironment(home, true)).not.toHaveProperty("CUDA_VISIBLE_DEVICES");
  });

  it("for a GPU render without prlimit still names the data-segment cap Blender sets itself", () => {
    expect(planSandbox("blender", "render.py", [], LIMITS, BARE_LINUX, "gpu").isolation.memory).toBe("setrlimit data segment, 2048 MB");
    expect(planSandbox("blender.exe", "render.py", [], LIMITS, WINDOWS, "gpu").isolation.memory).toBe("job object, 2048 MB, no child processes");
  });

  it("on Linux without unshare says the network is not isolated", () => {
    const plan = planSandbox("blender", "measure.py", [], LIMITS, BARE_LINUX);
    expect(plan.command).toBe("blender");
    expect(plan.isolation.network).toBe("not isolated");
    expect(plan.isolation.memory).toContain("setrlimit");
  });
});

describe("the sandbox on this machine", { timeout: 120_000 }, () => {
  const tools = detectTools();

  async function probe(mode: string, timeoutMs: number, device: SandboxDevice = "cpu") {
    const dir = freshDir("sandbox", `${mode}-${device}`);
    const out = join(dir, "probe.json");
    const plan = planSandbox(blenderPath(), PROBE, [SCRIPTS_DIR, mode, out], { ...LIMITS, timeoutMs }, tools, device);
    const run = await runSandboxed(plan, dir);
    return { run, plan, result: existsSync(out) ? JSON.parse(readFileSync(out, "utf8")) : undefined };
  }

  it("refuses memory over the cap on the CPU and starts Blender with its own empty user folders and no GPUs", async () => {
    const { result } = await probe("limits", 60_000);
    expect(result.memory).toBe("refused");
    expect(result.gpus).toEqual(["", ""]);
    expect(result.environment).toEqual(["BLENDER_USER_CONFIG", "BLENDER_USER_DATAFILES", "BLENDER_USER_EXTENSIONS", "BLENDER_USER_RESOURCES", "BLENDER_USER_SCRIPTS"]);
    if (tools.platform === "win32") expect(result.childProcess).toBe("blocked");
  });

  it.runIf(tools.platform === "linux")("has no network on the CPU when unshare is available", async () => {
    const { result, plan } = await probe("network", 60_000);
    expect(plan.isolation.network).toBe(tools.unshare ? "isolated" : "not isolated");
    if (tools.unshare) expect(result.network).toBe("unreachable");
  });

  it("refuses memory over the cap in the GPU sandbox too, with the GPUs visible", async () => {
    const { result, plan } = await probe("limits", 60_000, "gpu");
    expect(result.memory).toBe("refused");
    expect(result.gpus).toEqual([null, null]);
    if (tools.platform !== "win32") expect(result.limits.memoryKind).toBe("data");
    if (tools.platform === "linux") expect(plan.isolation.network).toBe(tools.unshare ? "isolated" : "not isolated");
    if (tools.platform === "linux" && tools.unshare) expect(result.network).toBe("unreachable");
  });

  it("stops Blender at the timeout", async () => {
    const started = Date.now();
    const { run, result } = await probe("sleep", 8_000);
    expect(run.timedOut).toBe(true);
    expect(result).toBeUndefined();
    expect(Date.now() - started).toBeLessThan(30_000);
  });
});
