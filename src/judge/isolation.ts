import { existsSync, readdirSync, readFileSync } from "node:fs";
import type { Tools } from "./sandbox.js";

export const CONTAINER_MARKERS = ["/.dockerenv", "/run/.containerenv"] as const;
export const INFRASTRUCTURE_EXIT = 75;

export type ContainerIsolation = {
  marker: string | null;
  interfaces: string[];
  rootReadOnly: boolean;
  memoryLimitBytes: number | null;
  uid: number | null;
};

export type ProbeSources = {
  exists: (path: string) => boolean;
  read: (path: string) => string | null;
  list: (path: string) => string[] | null;
  uid: () => number | null;
};

export class InfrastructureError extends Error {
  constructor(
    readonly code: "isolation" | "sandbox",
    message: string,
  ) {
    super(message);
    this.name = "InfrastructureError";
  }
}

const HOST_SOURCES: ProbeSources = {
  exists: (path) => existsSync(path),
  read: (path) => {
    try {
      return readFileSync(path, "utf8");
    } catch {
      return null;
    }
  },
  list: (path) => {
    try {
      return readdirSync(path);
    } catch {
      return null;
    }
  },
  uid: () => (typeof process.getuid === "function" ? process.getuid() : null),
};

function rootOptions(mountinfo: string): string | null {
  for (const line of mountinfo.split("\n")) {
    const fields = line.split(" ");
    if (fields[4] === "/") return fields[5] ?? null;
  }
  return null;
}

function memoryLimit(sources: ProbeSources): number | null {
  for (const path of ["/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"]) {
    const text = sources.read(path)?.trim();
    if (text === undefined || text === "max" || !/^\d+$/.test(text)) continue;
    const bytes = Number(text);
    if (bytes > 0 && bytes < 2 ** 62) return bytes;
  }
  return null;
}

export function probeContainer(platform: NodeJS.Platform = process.platform, sources: ProbeSources = HOST_SOURCES): ContainerIsolation | null {
  if (platform !== "linux") return null;
  const marker = CONTAINER_MARKERS.find((path) => sources.exists(path)) ?? null;
  if (marker === null) return null;
  const options = rootOptions(sources.read("/proc/self/mountinfo") ?? "");
  return {
    marker,
    interfaces: (sources.list("/sys/class/net") ?? ["unknown"]).filter((name) => name !== "lo").sort(),
    rootReadOnly: options !== null && options.split(",")[0] === "ro",
    memoryLimitBytes: memoryLimit(sources),
    uid: sources.uid(),
  };
}

export function containerShortfalls(container: ContainerIsolation): string[] {
  const missing: string[] = [];
  if (container.interfaces.length > 0) missing.push(`the container has a network (${container.interfaces.join(", ")}); run it with --network none`);
  if (!container.rootReadOnly) missing.push("the container's root filesystem is writable; run it with --read-only");
  if (container.memoryLimitBytes === null) missing.push("the container has no memory limit; run it with --memory");
  if (container.uid === null || container.uid === 0) missing.push("the container runs as root; run it as a non-root user");
  return missing;
}

export function containerText(container: ContainerIsolation): string {
  const memory = container.memoryLimitBytes === null ? "no memory limit" : `memory limit ${Math.round(container.memoryLimitBytes / 1048576)} MB`;
  const network = container.interfaces.length === 0 ? "no network" : `network ${container.interfaces.join(", ")}`;
  return `container (${container.marker}): ${network}, ${container.rootReadOnly ? "read-only root" : "writable root"}, ${memory}, uid ${container.uid ?? "unknown"}`;
}

export function hostShortfalls(tools: Tools): string[] {
  if (tools.platform === "win32") {
    return ["on Windows the judge's own sandbox is at most the low-integrity mode, which limits only writes: reads and the network stay open; judge paid work in the judge container, or pass --no-require-isolation for a local preview"];
  }
  if (tools.platform !== "linux") return [`the judge has no sandbox on ${tools.platform}; judge paid work in the judge container`];
  const missing: string[] = [];
  if (tools.mountNamespace !== true) missing.push("no container and no user, mount and PID namespaces (unshare cannot create them, or a read-only mount could not be confirmed): the host's files are not isolated");
  if (!tools.unshare) missing.push("no network namespace: the network is not isolated");
  if (!tools.prlimit) missing.push("no prlimit: no memory cap is set outside Blender");
  return missing;
}

export type IsolationCheck = { container: ContainerIsolation | null; shortfalls: string[] };

export function checkIsolation(tools: Tools, container: ContainerIsolation | null): IsolationCheck {
  const inContainer = container === null ? [] : containerShortfalls(container);
  if (container !== null && inContainer.length === 0) return { container, shortfalls: [] };
  const onHost = hostShortfalls(tools);
  return { container, shortfalls: onHost.length === 0 ? [] : [...inContainer, ...onHost] };
}

export function requireIsolation(check: IsolationCheck): void {
  if (check.shortfalls.length === 0) return;
  throw new InfrastructureError("isolation", `the judge refuses to run without isolation, and this is not a verdict: ${check.shortfalls.join("; ")}`);
}
