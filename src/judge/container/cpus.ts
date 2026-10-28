import { readFileSync } from "node:fs";

function read(path: string): string | null {
  try {
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
}

export function cpuQuota(cpuMax: string | null = read("/sys/fs/cgroup/cpu.max")): number | null {
  const [quota, period] = (cpuMax ?? "").trim().split(/\s+/);
  if (quota === undefined || period === undefined || quota === "max" || !/^\d+$/.test(quota) || !/^\d+$/.test(period) || Number(period) === 0) return null;
  return Number(quota) / Number(period);
}

export function allowedCpus(status: string | null = read("/proc/self/status")): number[] {
  const list = /^Cpus_allowed_list:\s*(\S+)/m.exec(status ?? "")?.[1];
  if (list === undefined) return [];
  return list.split(",").flatMap((part) => {
    const [first, last] = part.split("-").map(Number);
    if (first === undefined || !Number.isInteger(first)) return [];
    const end = last === undefined ? first : last;
    return Number.isInteger(end) && end >= first ? Array.from({ length: end - first + 1 }, (_, index) => first + index) : [];
  });
}

export function pinned(command: string, args: string[], quota: number | null = cpuQuota(), allowed: number[] = allowedCpus()): [string, string[]] {
  if (quota === null) return [command, args];
  const count = Math.max(1, Math.ceil(quota));
  if (allowed.length <= count) return [command, args];
  return ["taskset", ["-c", allowed.slice(0, count).join(","), command, ...args]];
}

export function jobsFor(env: NodeJS.ProcessEnv, quota: number | null = cpuQuota()): string {
  if (env["BLENDWORKS_JOBS"]) return env["BLENDWORKS_JOBS"];
  return quota !== null && quota < 4 ? "1" : "2";
}
