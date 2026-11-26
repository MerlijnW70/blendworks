import { readFileSync } from "node:fs";
import { availableParallelism } from "node:os";
import { blenderJobs, blenderThreads } from "../../src/blender.js";

const CGROUP_V2 = "/sys/fs/cgroup/cpu.max";
const CGROUP_V1 = ["/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "/sys/fs/cgroup/cpu/cpu.cfs_period_us"];

function read(path: string): string | undefined {
  try {
    return readFileSync(path, "utf8").trim();
  } catch {
    return undefined;
  }
}

export function quotaCpus(v2: string | undefined, v1: [string | undefined, string | undefined]): number | undefined {
  const [quota, period] = v2 !== undefined ? v2.split(/\s+/) : v1;
  if (quota === undefined || period === undefined || quota === "max" || Number(quota) <= 0 || Number(period) <= 0) return undefined;
  return Math.max(1, Math.ceil(Number(quota) / Number(period)));
}

export function testCpus(): number {
  const quota = quotaCpus(read(CGROUP_V2), [read(CGROUP_V1[0]!), read(CGROUP_V1[1]!)]);
  return Math.min(availableParallelism(), quota ?? Number.POSITIVE_INFINITY);
}

export function withThreadArguments(args: readonly string[] | undefined): string[] {
  const given = [...(args ?? [])];
  const background = given.some((arg) => arg === "--background" || arg === "-b");
  if (!background || given.some((arg) => arg === "--threads" || arg === "-t")) return given;
  return ["--threads", String(blenderThreads(blenderJobs(), testCpus())), ...given];
}
