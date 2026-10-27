import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { kernelCache, KERNELS, privateKernels, READY } from "../../src/judge/kernel-cache.js";
import { runSandboxed, type Plan } from "../../src/judge/sandbox.js";
import { scratch } from "../tooling/probes.js";

const saved = process.env["BLENDWORKS_CACHE"];
let root = "";

beforeEach(() => {
  root = scratch("kernel-cache");
  process.env["BLENDWORKS_CACHE"] = root;
});

afterEach(() => {
  if (saved === undefined) delete process.env["BLENDWORKS_CACHE"];
  else process.env["BLENDWORKS_CACHE"] = saved;
});

function trust(): string {
  const optix = join(kernelCache(root), KERNELS, "optix");
  mkdirSync(optix, { recursive: true });
  writeFileSync(join(optix, "optix7cache.db"), "warmed");
  writeFileSync(join(kernelCache(root), READY), "");
  return optix;
}

const WRITE_KERNEL = `
const fs = require("node:fs");
const path = require("node:path");
const folder = process.env.OPTIX_CACHE_PATH;
const seen = fs.readFileSync(path.join(folder, "optix7cache.db"), "utf8");
fs.writeFileSync(path.join(folder, "optix7cache.db"), "written by the run");
process.stdout.write(seen + "|" + folder);
`;

function gpuPlan(work: string): Plan {
  return { command: process.execPath, args: ["-e", WRITE_KERNEL], isolation: { network: "not isolated", memory: "none", timeoutMs: 30_000, platform: "test", filesystem: "not isolated", processes: "shared PID namespace" }, gpu: true, writable: [work], lowIntegrity: false };
}

describe("the GPU kernel cache of the judge", () => {
  it("gives each run a private copy of the kernels the warm-up compiled", () => {
    trust();
    const home = scratch("kernel-home");
    const variables = privateKernels(home, root);
    expect(variables["OPTIX_CACHE_PATH"]!.startsWith(home)).toBe(true);
    expect(readFileSync(join(variables["OPTIX_CACHE_PATH"]!, "optix7cache.db"), "utf8")).toBe("warmed");
  });

  it("starts empty before the warm-up has run", () => {
    const home = scratch("kernel-home");
    const variables = privateKernels(home, root);
    expect(existsSync(join(variables["OPTIX_CACHE_PATH"]!, "optix7cache.db"))).toBe(false);
  });

  it("lets a sandboxed GPU run read the warmed kernels, never write to the shared ones", async () => {
    const optix = trust();
    const work = join(root, "work");
    const result = await runSandboxed(gpuPlan(work), work);
    const [seen, folder] = result.output.split("|");
    expect(seen).toBe("warmed");
    expect(folder!.startsWith(work)).toBe(true);
    expect(readFileSync(join(optix, "optix7cache.db"), "utf8")).toBe("warmed");
    expect(readdirSync(work)).toEqual([]);
  });
});
