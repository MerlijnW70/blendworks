import { describe, expect, it } from "vitest";
import { blenderJobs, blenderThreadArguments, blenderThreads, cgroupCpuQuota, defaultJobs, HOST_JOBS, machineCpus } from "../../src/blender.js";

const NO_CGROUP = { v2: undefined, v1Quota: undefined, v1Period: undefined };
const quota = (cpus: number) => ({ ...NO_CGROUP, v2: `${cpus * 100_000} 100000` });

describe("Blender slots from the machine", () => {
  it("follow a faked cgroup CPU quota: one slot per two CPUs of the quota, at least one", () => {
    for (const [cpus, slots] of [[1, 1], [2, 1], [3, 1], [4, 2], [6, 3], [8, 4]] as const) {
      const machine = machineCpus(quota(cpus), 32);
      expect(machine).toEqual({ cpus, quota: cpus, source: "cgroup quota" });
      expect(blenderJobs({}, machine)).toBe(slots);
    }
  });

  it("read the cgroup v1 quota and round a fractional quota down, to at least one CPU", () => {
    expect(machineCpus({ v2: undefined, v1Quota: "250000", v1Period: "100000" }, 16)).toMatchObject({ cpus: 2, source: "cgroup quota" });
    expect(machineCpus({ ...NO_CGROUP, v2: "50000 100000" }, 16)).toMatchObject({ cpus: 1, source: "cgroup quota" });
    expect(machineCpus(quota(8), 4)).toMatchObject({ cpus: 4, source: "cgroup quota" });
  });

  it("keep the stated, lower host default without a quota, never more than the logical CPUs", () => {
    expect(cgroupCpuQuota({ ...NO_CGROUP, v2: "max 100000" })).toBeUndefined();
    expect(cgroupCpuQuota({ v2: undefined, v1Quota: "-1", v1Period: "100000" })).toBeUndefined();
    expect(HOST_JOBS).toBe(2);
    expect(blenderJobs({}, machineCpus({ ...NO_CGROUP, v2: "max 100000" }, 32))).toBe(HOST_JOBS);
    expect(defaultJobs(machineCpus(NO_CGROUP, 1))).toBe(1);
  });

  it("let BLENDWORKS_JOBS override the machine, in a sandbox and on a host", () => {
    expect(blenderJobs({ BLENDWORKS_JOBS: "2" }, machineCpus(quota(4), 32))).toBe(2);
    expect(blenderJobs({ BLENDWORKS_JOBS: "6" }, machineCpus(NO_CGROUP, 32))).toBe(6);
  });

  it("give each Blender process a --threads count that fits the slots", () => {
    for (const cpus of [1, 2, 4, 8, 32]) {
      for (const jobs of [1, 2, 3, 4, 8]) {
        const threads = blenderThreads(jobs, cpus, {});
        expect(threads).toBeGreaterThanOrEqual(1);
        if (jobs <= cpus) expect(threads * jobs).toBeLessThanOrEqual(cpus);
      }
    }
    expect(blenderThreads(4, 4, { BLENDWORKS_THREADS: "2" })).toBe(2);
    expect(() => blenderThreads(4, 4, { BLENDWORKS_THREADS: "0" })).toThrow(/BLENDWORKS_THREADS/);
    const judge = machineCpus(quota(4), 32);
    expect(blenderThreadArguments(blenderJobs({}, judge), judge.cpus, {})).toEqual(["--threads", "2"]);
  });
});
