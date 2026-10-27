import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkCache, formatFindings, nodeSupported, parseDevices, sandboxFindings } from "../../scripts/lib/doctor.js";
import { clean } from "../../scripts/lib/clean.js";
import { CACHE_MARKER, ensureCacheRoot } from "../../scripts/lib/paths.js";
import { acquireSlot } from "../../scripts/lib/slots.js";

function scratch(): string {
  return mkdtempSync(join(tmpdir(), "blendworks-doctor-"));
}

describe("npm run doctor", () => {
  it("accepts the Node versions the dependencies support and refuses the others", () => {
    for (const good of ["22.12.0", "22.22.1", "24.0.0", "26.1.0", "v24.3.0"]) expect(nodeSupported(good), good).toBe(true);
    for (const bad of ["20.19.0", "22.11.9", "23.5.0", "25.1.0", "18.0.0"]) expect(nodeSupported(bad), bad).toBe(false);
  });

  it("reads the device list the probe prints", () => {
    expect(parseDevices('noise\nDEVICES{"OPTIX":["RTX 4080"]}\n')).toEqual({ OPTIX: ["RTX 4080"] });
    expect(parseDevices("DEVICES{}")).toEqual({});
    expect(parseDevices("nothing")).toBeUndefined();
    expect(parseDevices("DEVICES{broken")).toBeUndefined();
  });

  it("warns, with a fix, when a Linux sandbox tool is missing", () => {
    const findings = sandboxFindings({ platform: "linux", unshare: false, prlimit: true });
    expect(findings.map((finding) => [finding.label, finding.status])).toEqual([
      ["unshare", "warn"],
      ["prlimit", "ok"],
    ]);
    expect(findings[0]?.fix).toContain("util-linux");
  });

  it("is quiet about the Windows sandbox, which has no tools to check", () => {
    const findings = sandboxFindings({ platform: "win32", unshare: false, prlimit: false });
    expect(findings).toHaveLength(1);
    expect(findings[0]?.status).toBe("ok");
  });

  it("prints a fix under each problem and a closing verdict", () => {
    const lines = formatFindings([
      { status: "ok", label: "Node", detail: "22.22.1" },
      { status: "fail", label: "Blender", detail: "not found", fix: "set BLENDER" },
      { status: "warn", label: "unshare", detail: "missing" },
    ]);
    expect(lines).toEqual(["ok    Node: 22.22.1", "fail  Blender: not found", "      fix: set BLENDER", "warn  unshare: missing", "1 problem to fix"]);
    expect(formatFindings([{ status: "warn", label: "x", detail: "y" }]).at(-1)).toBe("ready, with 1 warning");
    expect(formatFindings([{ status: "ok", label: "x", detail: "y" }]).at(-1)).toBe("ready");
  });

  it("reports the cache folder and whether the fixtures are there", () => {
    const root = scratch();
    const findings = checkCache(root, "5.2.3");
    expect(findings.map((finding) => finding.label)).toEqual(["Cache", "Judge fixtures"]);
    expect(findings[0]?.detail).toContain(root);
    expect(findings[1]?.detail).toContain("not generated yet");
  });
});

describe("npm run clean", () => {
  it("removes a Blendworks cache", () => {
    const root = join(scratch(), "cache");
    ensureCacheRoot(root);
    mkdirSync(join(root, "fixtures"));
    expect(clean(root, false).removed).toEqual([root]);
  });

  it("leaves a folder alone that is not a Blendworks cache", () => {
    const root = scratch();
    writeFileSync(join(root, "precious.txt"), "keep");
    const result = clean(root, false);
    expect(result.removed).toEqual([]);
    expect(result.refusal).toContain(CACHE_MARKER);
  });

  it("waits while Blender is running from the cache", async () => {
    const root = join(scratch(), "cache");
    const slot = await acquireSlot({ root, jobs: 1 });
    expect(clean(root, false).refusal).toContain("Blender is running");
    slot.release();
    expect(clean(root, false).removed).toEqual([root]);
  });
});
