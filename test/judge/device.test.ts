import { describe, expect, it } from "vitest";
import { chooseDevice, DeviceError, describeDevice, fallBackToCpu, parseDeviceMode, type BackendProbe } from "../../src/judge/device.js";
import { summarize, type Report } from "../../src/judge/report.js";
import { onDevice, StageFailure, type Attempt, type DeviceRequest } from "../../src/judge/stages.js";

const RTX = "NVIDIA GeForce RTX 4080";

function usable(backend: string, devices = [RTX]): BackendProbe {
  return { backend, devices, usable: true, reason: "" };
}

function broken(backend: string, reason: string, devices: string[] = []): BackendProbe {
  return { backend, devices, usable: false, reason };
}

describe("BLENDWORKS_DEVICE", () => {
  it("defaults to auto and reads auto, gpu and cpu in any case", () => {
    expect(parseDeviceMode(undefined)).toBe("auto");
    expect(parseDeviceMode("")).toBe("auto");
    expect(parseDeviceMode("AUTO")).toBe("auto");
    expect(parseDeviceMode(" gpu ")).toBe("gpu");
    expect(parseDeviceMode("Cpu")).toBe("cpu");
  });

  it("refuses anything else, naming the variable", () => {
    for (const value of ["cuda", "optix", "1", "gpu0"]) {
      expect(() => parseDeviceMode(value)).toThrow(DeviceError);
      expect(() => parseDeviceMode(value)).toThrow(/BLENDWORKS_DEVICE must be auto, gpu or cpu/);
    }
  });
});

describe("choosing the render device from a stubbed device list", () => {
  it("takes the first usable backend in the order OptiX, CUDA, HIP, Metal, oneAPI", () => {
    expect(chooseDevice("auto", [usable("CUDA"), usable("OPTIX")])).toEqual({ requested: "auto", kind: "gpu", backend: "OPTIX", devices: [RTX], fallback: null });
    expect(chooseDevice("auto", [usable("ONEAPI", ["Arc"]), usable("HIP", ["Radeon"]), usable("METAL", ["M3"])]).backend).toBe("HIP");
    expect(chooseDevice("auto", [usable("ONEAPI", ["Arc"]), usable("METAL", ["M3"])]).backend).toBe("METAL");
    expect(chooseDevice("gpu", [usable("ONEAPI", ["Arc"])]).backend).toBe("ONEAPI");
  });

  it("skips a backend whose device does not work or that lists no device", () => {
    const probes = [broken("OPTIX", "the test render failed", [RTX]), { ...usable("CUDA"), devices: [] }, usable("HIP", ["Radeon"])];
    expect(chooseDevice("auto", probes)).toMatchObject({ kind: "gpu", backend: "HIP", devices: ["Radeon"] });
  });

  it("falls back to the CPU under auto when no backend is usable, and says why", () => {
    const probes = [broken("OPTIX", "no device found"), broken("CUDA", "the test render failed: CUDA error", [RTX])];
    const device = chooseDevice("auto", probes);
    expect(device).toMatchObject({ requested: "auto", kind: "cpu", backend: null, devices: [] });
    expect(device.fallback).toBe("no usable GPU (OPTIX: no device found; CUDA: the test render failed: CUDA error)");
    expect(chooseDevice("auto", []).fallback).toBe("no usable GPU (no backend was probed)");
    expect(describeDevice(device)).toMatch(/^cpu \(auto fell back to the CPU with the original limits: no usable GPU/);
  });

  it("fails cleanly under gpu when no backend is usable, with the reason", () => {
    expect(() => chooseDevice("gpu", [broken("CUDA", "no device found")])).toThrow("BLENDWORKS_DEVICE=gpu, but no usable GPU (CUDA: no device found)");
  });

  it("uses the CPU under cpu even when a GPU works", () => {
    expect(chooseDevice("cpu", [usable("OPTIX")])).toEqual({ requested: "cpu", kind: "cpu", backend: null, devices: [], fallback: null });
  });

  it("falls back after a GPU that probed well fails to start, only under auto", () => {
    const device = chooseDevice("auto", [usable("CUDA")]);
    expect(fallBackToCpu(device, "no CUDA device starts").fallback).toBe("CUDA did not start inside the sandbox: no CUDA device starts");
    expect(() => fallBackToCpu(chooseDevice("gpu", [usable("CUDA")]), "no CUDA device starts")).toThrow(DeviceError);
  });

  it("describes the device the way the summary shows it", () => {
    expect(describeDevice(chooseDevice("auto", [usable("OPTIX")]))).toBe("gpu OPTIX (NVIDIA GeForce RTX 4080)");
    expect(describeDevice(chooseDevice("cpu", []))).toBe("cpu");
  });
});

type Script = (request: DeviceRequest) => Attempt<string> | "crash";

async function run(mode: "auto" | "gpu" | "cpu", script: Script) {
  const requests: DeviceRequest[] = [];
  const result = await onDevice(mode, ["OPTIX", "CUDA"], async (request) => {
    requests.push(request);
    const outcome = script(request);
    if (outcome === "crash") throw new StageFailure({ stage: "render", code: "crashed", message: "Blender exited with code 139" });
    return outcome;
  });
  return { ...result, requests };
}

const NO_GPU: Script = (request) =>
  request.device === "AUTO" ? { ok: false, message: "no GPU backend works inside the sandbox", probes: [broken("OPTIX", "no device found")] } : { ok: true, value: "cpu image", backend: "CPU", probes: [] };

describe("rendering on the chosen device", () => {
  it("renders once on the GPU sandbox when a GPU works", async () => {
    const { device, value, requests } = await run("auto", () => ({ ok: true, value: "gpu image", backend: "CUDA", probes: [broken("OPTIX", "no device found"), usable("CUDA")] }));
    expect(requests).toEqual([{ device: "AUTO", backends: ["OPTIX", "CUDA"], sandbox: "gpu" }]);
    expect(value).toBe("gpu image");
    expect(device).toMatchObject({ kind: "gpu", backend: "CUDA" });
  });

  it("under auto re-runs on the CPU with the original limits when no GPU starts in the sandbox", async () => {
    const { device, value, requests } = await run("auto", NO_GPU);
    expect(requests.map((request) => [request.device, request.sandbox])).toEqual([["AUTO", "gpu"], ["CPU", "cpu"]]);
    expect(value).toBe("cpu image");
    expect(device).toMatchObject({ kind: "cpu", fallback: "no usable GPU (OPTIX: no device found)" });
  });

  it("under auto re-runs on the CPU when Blender crashes in the GPU sandbox", async () => {
    const { device, requests } = await run("auto", (request) => (request.device === "AUTO" ? "crash" : { ok: true, value: "cpu image", backend: "CPU", probes: [] }));
    expect(requests.map((request) => request.sandbox)).toEqual(["gpu", "cpu"]);
    expect(device.fallback).toContain("Blender exited with code 139");
  });

  it("under gpu stops with a reason instead of using the CPU", async () => {
    await expect(run("gpu", NO_GPU)).rejects.toMatchObject({ failure: { stage: "device", code: "no_gpu" } });
    await expect(run("gpu", (request) => (request.device === "AUTO" ? "crash" : { ok: true, value: "", backend: "CPU", probes: [] }))).rejects.toMatchObject({
      failure: { code: "crashed" },
    });
  });

  it("under cpu never starts the GPU sandbox", async () => {
    const { device, requests } = await run("cpu", NO_GPU);
    expect(requests).toEqual([{ device: "CPU", backends: [], sandbox: "cpu" }]);
    expect(device).toMatchObject({ kind: "cpu", fallback: null });
  });
});

describe("the summary", () => {
  const isolation = (memory: string) => ({ network: "isolated" as const, memory, timeoutMs: 300_000, platform: "linux" });
  const draft: Omit<Report, "summary"> = {
    passed: true,
    preview: false,
    spec: { path: "spec.json", sha256: null, name: "steam drill rig" },
    asset: { path: "rig.glb", sha256: null, bytes: 1 },
    blender: "5.2.3",
    sandbox: isolation("prlimit address space, 4096 MB"),
    renderSandbox: isolation("prlimit data segment, 4096 MB"),
    device: chooseDevice("auto", [usable("CUDA")]),
    failure: null,
    rules: [{ rule: "format", measured: "glb", limit: "glb", pass: true }],
    measurements: null,
    renders: null,
    timings: { measure: 2.5, device: 0.8, render: 5.2, sheet: 0.25, total: 9 },
  };

  it("names the GPU, both sandboxes and the stage times", () => {
    const lines = summarize(draft).split("\n");
    expect(lines).toContain("  render: gpu CUDA (NVIDIA GeForce RTX 4080)");
    expect(lines).toContain("  sandbox: network isolated; memory prlimit address space, 4096 MB; timeout 300 s");
    expect(lines).toContain("  render sandbox: network isolated; memory prlimit data segment, 4096 MB; timeout 300 s");
    expect(lines).toContain("  time: measure 2.50 s, device 0.80 s, render 5.20 s, sheet 0.25 s, total 9.00 s");
  });

  it("shows one sandbox line when the render ran under the same limits", () => {
    const text = summarize({ ...draft, device: chooseDevice("cpu", []), renderSandbox: draft.sandbox, timings: { ...draft.timings, device: null } });
    expect(text).toContain("  render: cpu\n");
    expect(text).not.toContain("render sandbox");
    expect(text).toContain("  time: measure 2.50 s, render 5.20 s, sheet 0.25 s, total 9.00 s");
  });
});
