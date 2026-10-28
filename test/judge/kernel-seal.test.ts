import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { warmKernels } from "../../src/judge/gpu-cache.js";
import { hashKernels, kernelCache, KERNELS, kernelsIntact, MANIFEST, privateKernels, READY, readManifest, sealKernels, UNAVAILABLE } from "../../src/judge/kernel-cache.js";
import { DEFAULT_BACKENDS, DEFAULTS } from "../../src/judge/stages.js";
import { detectTools, LOW_INTEGRITY_SCRIPT, lowerIntegrity } from "../../src/judge/sandbox.js";
import { scratch } from "../tooling/probes.js";
import { useBlenderSlot } from "../setup/slot.js";
import { workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const saved = process.env["BLENDWORKS_CACHE"];
let root = "";

beforeEach(() => {
  root = scratch("kernel-seal");
  process.env["BLENDWORKS_CACHE"] = root;
});

afterEach(() => {
  if (saved === undefined) delete process.env["BLENDWORKS_CACHE"];
  else process.env["BLENDWORKS_CACHE"] = saved;
});

function warmed(contents: Record<string, string> = { "optix/optix7cache.db": "warmed", "cuda/ComputeCache/index": "index" }): string {
  const trusted = kernelCache(root);
  for (const [name, text] of Object.entries(contents)) {
    mkdirSync(join(trusted, KERNELS, name, ".."), { recursive: true });
    writeFileSync(join(trusted, KERNELS, name), text);
  }
  writeFileSync(join(trusted, READY), "");
  expect(sealKernels(trusted)).toBe(true);
  return trusted;
}

const LOW_WRITE = `
import json, os, sys
folder = sys.argv[1]
result = {}
for name, path in (("new", os.path.join(folder, "planted.bin")), ("existing", os.path.join(folder, "optix", "optix7cache.db"))):
    try:
        with open(path, "a") as handle:
            handle.write("poisoned")
        result[name] = "written"
    except OSError as error:
        result[name] = "refused"
print(json.dumps(result))
`;

describe("the kernels are hash-checked before each copy", () => {
  it("records the sha256 of every kernel file when the warm-up ends", () => {
    const trusted = warmed();
    expect(Object.keys(readManifest(trusted) ?? {})).toEqual(["cuda/ComputeCache/index", "optix/optix7cache.db"]);
    expect(readManifest(trusted)).toEqual(hashKernels(join(trusted, KERNELS)));
    expect(kernelsIntact(trusted)).toBe(true);
  });

  it("copies nothing and drops the cache when a kernel changed, a file was planted or the manifest is gone", () => {
    for (const tamper of [
      (trusted: string) => writeFileSync(join(trusted, KERNELS, "optix", "optix7cache.db"), "poisoned"),
      (trusted: string) => writeFileSync(join(trusted, KERNELS, "optix", "planted.bin"), "extra"),
      (trusted: string) => writeFileSync(join(trusted, MANIFEST), "{}"),
    ]) {
      const trusted = warmed();
      tamper(trusted);
      expect(kernelsIntact(trusted)).toBe(false);
      const variables = privateKernels(scratch("kernel-seal-home"), root);
      expect(existsSync(join(variables["OPTIX_CACHE_PATH"]!, "optix7cache.db"))).toBe(false);
      expect(existsSync(trusted)).toBe(false);
    }
  });

  it("gives a verified copy when nothing changed", () => {
    warmed();
    const variables = privateKernels(scratch("kernel-seal-home"), root);
    expect(readFileSync(join(variables["OPTIX_CACHE_PATH"]!, "optix7cache.db"), "utf8")).toBe("warmed");
  });
});

describe("the warmed cache on this machine", workBudget(240_000), () => {
  const blender = blenderPath();
  const tools = detectTools(blender);
  const sandbox = { blender, limits: { timeoutMs: 120_000, memoryBytes: DEFAULTS.memoryBytes }, tools, workDir: "", delivery: "" };

  it.runIf(tools.platform === "win32" && typeof tools.lowIntegrityPython === "string")("is not writable by a low-integrity process after the warm run", () => {
    const trusted = kernelCache(root);
    mkdirSync(join(trusted, KERNELS), { recursive: true });
    lowerIntegrity(join(trusted, KERNELS));
    mkdirSync(join(trusted, KERNELS, "optix"), { recursive: true });
    writeFileSync(join(trusted, KERNELS, "optix", "optix7cache.db"), "warmed");
    const python = tools.lowIntegrityPython!;
    const probe = (): Record<string, string> => {
      const run = spawnSync(python, ["-I", LOW_INTEGRITY_SCRIPT, "--", python, "-I", "-c", LOW_WRITE, join(trusted, KERNELS)], { encoding: "utf8", timeout: 30_000, windowsHide: true });
      return JSON.parse(run.stdout.trim().split("\n").at(-1)!) as Record<string, string>;
    };
    expect(probe()).toEqual({ new: "written", existing: "written" });
    writeFileSync(join(trusted, KERNELS, "optix", "optix7cache.db"), "warmed");
    rmSync(join(trusted, KERNELS, "planted.bin"), { force: true });
    writeFileSync(join(trusted, READY), "");
    expect(sealKernels(trusted)).toBe(true);
    expect(probe()).toEqual({ new: "refused", existing: "refused" });
    expect(kernelsIntact(trusted)).toBe(true);
  });

  it("rebuilds a cache whose kernels no longer match their hashes", async () => {
    const trusted = warmed({ "optix/optix7cache.db": "stale" });
    writeFileSync(join(trusted, KERNELS, "optix", "optix7cache.db"), "poisoned");
    await warmKernels(sandbox, DEFAULT_BACKENDS, root);
    const optix = join(trusted, KERNELS, "optix", "optix7cache.db");
    expect(existsSync(optix) && readFileSync(optix, "utf8") === "poisoned").toBe(false);
    expect(existsSync(join(trusted, UNAVAILABLE)) || kernelsIntact(trusted)).toBe(true);
  });
});
