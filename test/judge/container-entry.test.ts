import { mkdirSync, symlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { allowedCpus, cpuQuota, jobsFor, pinned } from "../../src/judge/container/cpus.js";
import { main } from "../../src/judge/container/entry.js";
import { assetSpecFrom, inputPath, layoutFrom, mainAsset } from "../../src/judge/container/inputs.js";
import { ASSET_LIMITS, assetLimits } from "../../src/judge/container/asset.js";
import { CHECK_LIMITS, checkLimits, patchPaths, runCheck } from "../../src/judge/container/patch.js";
import { EntryError, parseResult, RESULT_PREFIX } from "../../src/judge/container/result.js";
import { containerShortfalls, probeContainer } from "../../src/judge/isolation.js";
import { freshDir } from "./helpers.js";

function folders() {
  const root = freshDir("container-entry", "judge");
  for (const name of ["work", "spec"]) mkdirSync(join(root, name), { recursive: true });
  writeFileSync(join(root, "secret.txt"), "outside");
  return root;
}

function refused(action: () => unknown): EntryError {
  try {
    action();
  } catch (error) {
    if (error instanceof EntryError) return error;
    throw error;
  }
  throw new Error("expected a refusal");
}

describe("the entry points' input folder", () => {
  it("accepts only paths inside the input folder, after links are resolved", () => {
    const root = folders();
    writeFileSync(join(root, "work", "crate.glb"), "glb");
    expect(inputPath(join(root, "work"), join(root, "work", "crate.glb"), "artifact")).toMatch(/crate\.glb$/);
    expect(refused(() => inputPath(join(root, "work"), join(root, "secret.txt"), "artifact"))).toMatchObject({ verdict: "error" });
    expect(refused(() => inputPath(join(root, "work"), join(root, "work", "..", "secret.txt"), "artifact")).message).toContain("outside the input folder");
    expect(refused(() => inputPath(join(root, "work"), undefined, "artifact")).message).toContain("no artifact was given");
    expect(refused(() => inputPath(join(root, "work"), join(root, "work", "missing.glb"), "artifact")).message).toContain("does not exist");
    let linked = false;
    try {
      symlinkSync(join(root, "secret.txt"), join(root, "work", "link.glb"));
      linked = true;
    } catch {
      linked = false;
    }
    if (linked) expect(refused(() => inputPath(join(root, "work"), join(root, "work", "link.glb"), "artifact")).message).toContain("outside the input folder");
  });

  it("finds the one asset of a delivered folder and fails a folder with none or two", () => {
    const root = folders();
    const delivered = join(root, "work", "delivery");
    mkdirSync(delivered, { recursive: true });
    writeFileSync(join(delivered, "crate.gltf"), "{}");
    writeFileSync(join(delivered, "crate.bin"), "bin");
    expect(mainAsset(delivered, join(root, "work"))).toMatch(/crate\.gltf$/);
    writeFileSync(join(delivered, "other.glb"), "glb");
    expect(refused(() => mainAsset(delivered, join(root, "work")))).toMatchObject({ verdict: "fail" });
    writeFileSync(join(root, "work", "notes.txt"), "text");
    expect(refused(() => mainAsset(join(root, "work", "notes.txt"), join(root, "work")))).toMatchObject({ verdict: "fail" });
  });

  it("reads the asset spec from the job spec's first json block, or from plain JSON", () => {
    expect(assetSpecFrom('# Job\n\ntext\n\n```json\n{ "format": "glb" }\n```\n\n```json\n{ "format": "fbx" }\n```\n')).toEqual({ format: "glb" });
    expect(assetSpecFrom('{ "format": "obj" }')).toEqual({ format: "obj" });
    expect(refused(() => assetSpecFrom("# Job\n\n```sh\nnpm test\n```\n"))).toMatchObject({ verdict: "error" });
  });

  it("uses Solive's folders by default", () => {
    expect(layoutFrom({})).toMatchObject({ root: "/judge", work: join("/judge", "work"), spec: join("/judge", "spec"), scratch: "/tmp/blendworks", blendworks: "/opt/blendworks", blender: "/opt/blender/blender" });
  });
});

describe("the patch entry point", () => {
  it("lists every path a patch touches, quoted or renamed", () => {
    const patch = [
      "From abc Mon Sep 17 00:00:00 2001",
      "Subject: [PATCH] Job",
      "--- a summary line in the message, not a path",
      "---",
      "diff --git a/src/a.ts b/src/a.ts",
      "--- a/src/a.ts",
      "+++ b/src/a.ts",
      'diff --git "a/docs/with space\\303\\251.md" "b/docs/with space\\303\\251.md"',
      "similarity index 90%",
      "rename from old/name.ts",
      "rename to new/name.ts",
    ].join("\n");
    expect(patchPaths(patch)).toEqual({ paths: ["docs/with spaceé.md", "new/name.ts", "old/name.ts", "src/a.ts"], refused: [] });
  });

  it("refuses paths outside the repository, into .git, absolute paths, links and submodules", () => {
    const refusals = (text: string) => patchPaths(text).refused;
    expect(refusals("diff --git a/../x b/../x\n--- a/../x\n+++ b/../x\n")[0]).toContain("leaves the asset folder");
    expect(refusals("diff --git a/.git/config b/.git/config\n")[0]).toContain("may not touch .git");
    expect(refusals("diff --git a/.GIT/hooks/post-merge b/.GIT/hooks/post-merge\n")[0]).toContain("may not touch .git");
    expect(refusals("--- /etc/passwd\n+++ /etc/passwd\n")[0]).toContain("absolute");
    expect(refusals("diff --git a/link b/link\nnew file mode 120000\n")[0]).toContain("links and submodules are refused");
    expect(refusals("diff --git a/vendor b/vendor\nnew file mode 160000\n")[0]).toContain("links and submodules are refused");
    expect(refusals("diff --git a/C:/x b/C:/x\n")[0]).toContain("drive");
  });
});

const container = probeContainer();
const sealed = container !== null && containerShortfalls(container).length === 0;

describe("the entry points' result", () => {
  it("is one JSON line the judge can read back, after any other output", () => {
    const line = `${RESULT_PREFIX}${JSON.stringify({ blendworks: "judge-result", verdict: "pass", exitCode: 0 })}`;
    expect(parseResult(`judge output\n${line}\n`)).toMatchObject({ verdict: "pass", exitCode: 0 });
    expect(parseResult("no result here")).toBeNull();
  });

  it.runIf(sealed === false)("refuses to judge outside a sealed container, and says so in its result", async () => {
    const scratch = freshDir("container-entry", "scratch");
    let output = "";
    const write = process.stdout.write.bind(process.stdout);
    process.stdout.write = ((chunk: string) => {
      output += chunk;
      return true;
    }) as typeof process.stdout.write;
    let code: number;
    try {
      code = await main(["asset"], { BLENDWORKS_SCRATCH: scratch, BLENDWORKS_INPUT_ROOT: scratch });
    } finally {
      process.stdout.write = write;
    }
    expect(code).toBe(75);
    expect(parseResult(output)).toMatchObject({ kind: "asset", verdict: "error", reason: expect.stringContaining("refuses to run outside a sealed container") });
  });
});

describe("the CPUs an entry point uses", () => {
  it("pins its children to as many CPUs as the container's quota allows, so thread pools fit the process limit", () => {
    expect(cpuQuota("800000 100000\n")).toBe(8);
    expect(cpuQuota("max 100000\n")).toBeNull();
    expect(allowedCpus("Name:\tnode\nCpus_allowed_list:\t0-3,8,10-11\n")).toEqual([0, 1, 2, 3, 8, 10, 11]);
    expect(pinned("npm", ["run", "check"], 2.5, [0, 1, 2, 3, 4, 5])).toEqual(["taskset", ["-c", "0,1,2", "npm", "run", "check"]]);
    expect(pinned("npm", ["run", "check"], null, [0, 1, 2, 3])).toEqual(["npm", ["run", "check"]]);
    expect(pinned("npm", ["run", "check"], 8, [0, 1, 2, 3])).toEqual(["npm", ["run", "check"]]);
    expect(jobsFor({}, 8)).toBe("2");
    expect(jobsFor({}, 2)).toBe("1");
    expect(jobsFor({ BLENDWORKS_JOBS: "1" }, 8)).toBe("1");
  });
});

describe("the check's own time limits", () => {
  it("stops a check that runs past its limit or goes quiet, as a fail of the check, not a judge timeout", async () => {
    const folder = freshDir("container-entry", "limits");
    const hang = [process.execPath, ["-e", "setInterval(() => process.stdout.write('.'), 100)"]] as [string, string[]];
    const quiet = [process.execPath, ["-e", "setTimeout(() => undefined, 60000)"]] as [string, string[]];
    const done = [process.execPath, ["-e", "process.exitCode = 0"]] as [string, string[]];
    const write = process.stdout.write.bind(process.stdout);
    process.stdout.write = (() => true) as typeof process.stdout.write;
    try {
      expect((await runCheck(folder, process.env, { total: 1, quiet: 30 }, hang)).stopped).toBe("npm run check ran past its 1 s limit");
      expect((await runCheck(folder, process.env, { total: 30, quiet: 1 }, quiet)).stopped).toBe("npm run check printed nothing for 1 s");
      expect(await runCheck(folder, process.env, { total: 30, quiet: 30 }, done)).toMatchObject({ code: 0, stopped: null });
    } finally {
      process.stdout.write = write;
    }
  });

  it("reads its limits from the container's environment, with defaults under the judge's timeout", () => {
    expect(checkLimits({})).toEqual(CHECK_LIMITS);
    expect(CHECK_LIMITS.total).toBeLessThan(3600);
    expect(checkLimits({ BLENDWORKS_CHECK_SECONDS: "1200", BLENDWORKS_QUIET_SECONDS: "x" })).toEqual({ total: 1200, quiet: CHECK_LIMITS.quiet });
    expect(assetLimits({ BLENDWORKS_RENDER_SECONDS: "300" })).toEqual({ ...ASSET_LIMITS, render: 300 });
    expect(ASSET_LIMITS.total).toBeLessThan(3600);
  });
});
