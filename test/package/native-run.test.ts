import { createServer } from "node:net";
import { existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { LOW_INTEGRITY_SCRIPT, MOUNT_SCRIPT, NAMESPACE_FLAGS, SYSTEM_READ_ONLY, type Tools } from "../../src/judge/sandbox.js";
import { WINDOWS_LAUNCHER, planNative, runNative } from "../../src/package/native-run.js";
import { defaultTools } from "../../src/package/native.js";

const MEGABYTE = 1024 * 1024;
const LIMITS = { timeoutMs: 20_000, memoryBytes: 2048 * MEGABYTE };
const NODE = process.execPath;
const REAL = defaultTools();
const HOSTILE = ["a b", "$(whoami)", "&& echo hi", "'single'", '"double"', "semi;colon", "back`tick`", "*", "line\nbreak"];

function names(): string[] {
  return readdirSync(tmpdir()).filter((name) => name.startsWith("blendworks-native-"));
}

describe("planning the sandbox of the native binary", () => {
  const binary = "/opt/tools/gltfpack";
  const args = ["-i", "input.glb", ...HOSTILE];

  it("on Linux with a mount namespace: no network, read-only system and tool, a memory cap, and the arguments untouched", () => {
    const tools: Tools = { platform: "linux", unshare: true, prlimit: true, mountNamespace: true };
    const plan = planNative(binary, args, LIMITS, tools, "/work/job");
    expect(plan.command).toBe("unshare");
    expect(plan.args.slice(0, NAMESPACE_FLAGS.length)).toEqual([...NAMESPACE_FLAGS]);
    expect(NAMESPACE_FLAGS).toContain("--net");
    expect(plan.args.slice(NAMESPACE_FLAGS.length, NAMESPACE_FLAGS.length + 2)).toEqual(["sh", MOUNT_SCRIPT]);
    const readOnly = plan.args.slice(plan.args.indexOf("--") + 1, plan.args.lastIndexOf("--"));
    for (const folder of SYSTEM_READ_ONLY) expect(readOnly).toContain(folder);
    expect(readOnly).toContain("/opt/tools");
    expect(plan.args.slice(-(args.length + 5))).toEqual(["prlimit", `--as=${LIMITS.memoryBytes}`, "--core=0", "--", binary, ...args]);
    expect(plan.writable).toEqual(["/work/job"]);
    expect(plan.isolation).toMatchObject({ network: "isolated", processes: "own PID namespace", timeoutMs: LIMITS.timeoutMs });
    expect(plan.isolation.memory).toBe("prlimit address space, 2048 MB");
    expect(plan.lowIntegrity).toBe(false);
  });

  it("on Linux without a mount namespace: still no network, and says the filesystem is not isolated", () => {
    const plan = planNative(binary, args, LIMITS, { platform: "linux", unshare: true, prlimit: true, mountNamespace: false }, "/work/job");
    expect(plan.command).toBe("unshare");
    expect(plan.args).toEqual(["-rn", "prlimit", `--as=${LIMITS.memoryBytes}`, "--core=0", "--", binary, ...args]);
    expect(plan.isolation.network).toBe("isolated");
    expect(plan.isolation.filesystem).toContain("not isolated");
  });

  it("on Linux with neither tool: runs the binary directly and admits there is no isolation and no cap", () => {
    const plan = planNative(binary, args, LIMITS, { platform: "linux", unshare: false, prlimit: false }, "/work/job");
    expect(plan.command).toBe(binary);
    expect(plan.args).toEqual(args);
    expect(plan.isolation).toMatchObject({ network: "not isolated" });
    expect(plan.isolation.memory).toContain("not capped");
  });

  it("on Windows with the low-integrity launcher: a job object with the memory cap, one process, and the arguments as an array", () => {
    const plan = planNative("C:\\tools\\gltfpack.exe", args, LIMITS, { platform: "win32", unshare: false, prlimit: false, lowIntegrityPython: "C:\\blender\\python.exe" }, "C:\\work");
    expect(plan.command).toBe("C:\\blender\\python.exe");
    expect(plan.args.slice(0, 3)).toEqual(["-I", "-c", WINDOWS_LAUNCHER]);
    expect(plan.args.slice(3)).toEqual([LOW_INTEGRITY_SCRIPT, String(LIMITS.memoryBytes), "C:\\tools\\gltfpack.exe", ...args]);
    expect(plan.lowIntegrity).toBe(true);
    expect(plan.isolation.memory).toBe("job object, 2048 MB per process");
    expect(plan.isolation.network).toBe("not isolated");
    expect(WINDOWS_LAUNCHER).toContain("ProcessMemoryLimit = limit");
    expect(WINDOWS_LAUNCHER).toContain("ActiveProcessLimit = 1");
  });

  it("on Windows without the launcher: runs directly and says the memory is not capped", () => {
    const plan = planNative("C:\\tools\\gltfpack.exe", args, LIMITS, { platform: "win32", unshare: false, prlimit: false, lowIntegrityPython: null }, "C:\\work");
    expect(plan.command).toBe("C:\\tools\\gltfpack.exe");
    expect(plan.args).toEqual(args);
    expect(plan.isolation.memory).toBe("not capped");
  });
});

describe("running a program in that sandbox", () => {
  it("passes every argument exactly as given, with no shell in between", async () => {
    const result = await runNative({ binary: NODE, args: ["-e", "console.log(JSON.stringify(process.argv.slice(1)))", ...HOSTILE], limits: LIMITS, tools: REAL });
    expect(result.code).toBe(0);
    expect(JSON.parse(result.log.trim().split("\n").at(-1)!)).toEqual(HOSTILE);
  });

  it("gives the program its input in a private work folder as the current folder, collects its output, and removes the folder", async () => {
    const before = names();
    const script = "const fs=require('fs');fs.writeFileSync('output.bin',Buffer.from(fs.readFileSync('input.bin')).reverse())";
    const result = await runNative({ binary: NODE, args: ["-e", script], limits: LIMITS, tools: REAL, input: { name: "input.bin", data: new Uint8Array([1, 2, 3, 4]) }, output: "output.bin" });
    expect(result.code).toBe(0);
    expect(Array.from(result.output ?? [])).toEqual([4, 3, 2, 1]);
    expect(names()).toEqual(before);
  });

  it("reports no output when the program writes none, and passes on its exit code and its messages", async () => {
    const result = await runNative({ binary: NODE, args: ["-e", "console.error('bad input');process.exit(3)"], limits: LIMITS, tools: REAL, output: "output.bin" });
    expect(result).toMatchObject({ code: 3, timedOut: false, output: null });
    expect(result.log).toContain("bad input");
  });

  it("stops a program that runs past the timeout", async () => {
    const started = performance.now();
    const result = await runNative({ binary: NODE, args: ["-e", "setTimeout(()=>{},60000)"], limits: { ...LIMITS, timeoutMs: 800 }, tools: REAL });
    expect(result.timedOut).toBe(true);
    expect(performance.now() - started).toBeLessThan(15_000);
    expect(existsSync(NODE)).toBe(true);
  });

  it.runIf(process.platform === "linux" && REAL.prlimit)("applies the memory cap to the process", async () => {
    const result = await runNative({ binary: "/bin/sh", args: ["-c", "ulimit -v"], limits: { timeoutMs: 20_000, memoryBytes: 3000 * MEGABYTE }, tools: REAL });
    expect(result.log.trim()).toBe(String((3000 * MEGABYTE) / 1024));
  });

  it.runIf(process.platform === "win32" && typeof REAL.lowIntegrityPython === "string")("applies the memory cap to the process through a job object", async () => {
    const allocate = "const b=Buffer.alloc(1200*1024*1024,1);console.log('allocated',b.length)";
    const capped = await runNative({ binary: NODE, args: ["-e", allocate], limits: { timeoutMs: 30_000, memoryBytes: 512 * MEGABYTE }, tools: REAL });
    expect(capped.log).not.toContain("allocated");
    const roomy = await runNative({ binary: NODE, args: ["-e", allocate], limits: { timeoutMs: 30_000, memoryBytes: 4096 * MEGABYTE }, tools: REAL });
    expect(roomy.log).toContain("allocated 1258291200");
  });

  it.runIf(process.platform === "linux" && REAL.unshare)("cuts the network", async () => {
    const server = createServer((socket) => socket.end("open"));
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const port = typeof address === "object" && address !== null ? address.port : 0;
    try {
      const script = `require('net').connect(${port},'127.0.0.1').on('connect',()=>{console.log('reached');process.exit(0)}).on('error',(e)=>{console.log('blocked '+e.code);process.exit(0)})`;
      const result = await runNative({ binary: NODE, args: ["-e", script], limits: LIMITS, tools: REAL });
      expect(result.log).toContain("blocked");
      expect(result.log).not.toContain("reached");
    } finally {
      server.close();
    }
  });
});
