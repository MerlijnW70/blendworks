export const DEVICE_MODES = ["auto", "gpu", "cpu"] as const;
export type DeviceMode = (typeof DEVICE_MODES)[number];

export const GPU_BACKENDS = ["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"] as const;

export const DEVICE_VARIABLE = "BLENDWORKS_DEVICE";

export type BackendProbe = { backend: string; devices: string[]; usable: boolean; reason: string };

export type RenderDevice = {
  requested: DeviceMode;
  kind: "gpu" | "cpu";
  backend: string | null;
  devices: string[];
  fallback: string | null;
};

export class DeviceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DeviceError";
  }
}

export function parseDeviceMode(value: string | undefined): DeviceMode {
  const text = (value ?? "").trim().toLowerCase();
  if (text === "") return "auto";
  const mode = DEVICE_MODES.find((candidate) => candidate === text);
  if (mode === undefined) throw new DeviceError(`${DEVICE_VARIABLE} must be auto, gpu or cpu, not "${value}"`);
  return mode;
}

export function deviceModeFromEnvironment(): DeviceMode {
  return parseDeviceMode(process.env[DEVICE_VARIABLE]);
}

function cpu(requested: DeviceMode, fallback: string | null): RenderDevice {
  return { requested, kind: "cpu", backend: null, devices: [], fallback };
}

export function noGpuReason(probes: BackendProbe[]): string {
  const tried = probes.map((probe) => `${probe.backend}: ${probe.reason || "not usable"}`);
  return tried.length > 0 ? `no usable GPU (${tried.join("; ")})` : "no usable GPU (no backend was probed)";
}

export function chooseDevice(mode: DeviceMode, probes: BackendProbe[]): RenderDevice {
  if (mode === "cpu") return cpu(mode, null);
  for (const backend of GPU_BACKENDS) {
    const probe = probes.find((candidate) => candidate.backend === backend);
    if (probe?.usable === true && probe.devices.length > 0) {
      return { requested: mode, kind: "gpu", backend, devices: [...probe.devices], fallback: null };
    }
  }
  const reason = noGpuReason(probes);
  if (mode === "gpu") throw new DeviceError(`${DEVICE_VARIABLE}=gpu, but ${reason}`);
  return cpu(mode, reason);
}

export function fallBackToCpu(device: RenderDevice, reason: string): RenderDevice {
  const message = `${device.backend ?? "the GPU"} did not start inside the sandbox: ${reason}`;
  if (device.requested === "gpu") throw new DeviceError(`${DEVICE_VARIABLE}=gpu, but ${message}`);
  return cpu(device.requested, message);
}

export function describeDevice(device: RenderDevice): string {
  if (device.kind === "gpu") return `gpu ${device.backend} (${device.devices.join(", ")})`;
  return device.fallback === null ? "cpu" : `cpu (auto fell back to the CPU with the original limits: ${device.fallback})`;
}
