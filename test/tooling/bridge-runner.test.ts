import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { BlenderNotFoundError, resolveBlender } from "../../src/blender.js";
import { listBridgeTests, runPool, selectTests, slowestFirst, summarize } from "../../scripts/lib/bridge-runner.js";

const FILES = ["test_addon.py", "test_bake.py", "test_bake_failures.py", "test_render.py", "test_smoke.py"];

describe("bridge test filters", () => {
  it("selects everything without a filter", () => {
    expect(selectTests(FILES, [])).toEqual(FILES);
  });

  it("matches a file by full name, stem or part of the name", () => {
    expect(selectTests(FILES, ["test_render"])).toEqual(["test_render.py"]);
    expect(selectTests(FILES, ["test_render.py"])).toEqual(["test_render.py"]);
    expect(selectTests(FILES, ["render"])).toEqual(["test_render.py"]);
    expect(selectTests(FILES, ["bridge/tests/test_smoke.py"])).toEqual(["test_smoke.py"]);
  });

  it("takes several filters together and keeps the file order", () => {
    expect(selectTests(FILES, ["smoke", "bake"])).toEqual(["test_bake.py", "test_bake_failures.py", "test_smoke.py"]);
  });

  it("selects nothing for a name that matches no file", () => {
    expect(selectTests(FILES, ["test_nothing"])).toEqual([]);
  });

  it("lists the repository's own bridge test files", () => {
    expect(listBridgeTests()).toContain("test_smoke.py");
  });
});

describe("the bridge test pool", () => {
  it("never runs more than the limit at once, and finishes every item", async () => {
    let running = 0;
    let peak = 0;
    const done: number[] = [];
    const items = Array.from({ length: 9 }, (_, index) => index);
    const results = await runPool(items, 3, async (item) => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((resolveWait) => setTimeout(resolveWait, 20));
      running -= 1;
      done.push(item);
      return item * 2;
    });
    expect(peak).toBe(3);
    expect(results).toEqual(items.map((item) => item * 2));
    expect(done.sort((a, b) => a - b)).toEqual(items);
  });

  it("runs one at a time with a limit of 1", async () => {
    let running = 0;
    let peak = 0;
    await runPool([1, 2, 3, 4], 1, async () => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((resolveWait) => setTimeout(resolveWait, 5));
      running -= 1;
    });
    expect(peak).toBe(1);
  });

  it("starts the files that took longest last time first, and new files before all", () => {
    expect(slowestFirst(["a", "b", "c", "d"], { a: 1, b: 9, c: 4 })).toEqual(["d", "b", "c", "a"]);
  });

  it("reports the slowest files and the count", () => {
    const lines = summarize(
      [
        { file: "test_a.py", passed: true, seconds: 1.2, output: "" },
        { file: "test_b.py", passed: false, seconds: 7.5, output: "" },
        { file: "test_c.py", passed: true, seconds: 3.1, output: "" },
      ],
      8.4,
    );
    expect(lines[0]).toBe("2 of 3 bridge test files passed in 8.4 s");
    expect(lines[1]).toBe("slowest: test_b.py 7.5 s, test_c.py 3.1 s, test_a.py 1.2 s");
  });
});

function blenderAvailable(): boolean {
  try {
    resolveBlender();
    return true;
  } catch (error) {
    if (error instanceof BlenderNotFoundError) return false;
    throw error;
  }
}

describe.skipIf(!blenderAvailable())("npm run test:bridge", { timeout: 120_000 }, () => {
  const run = (...args: string[]) =>
    spawnSync(process.execPath, ["--import", "tsx", resolve("scripts", "bridge-tests.mjs"), ...args], { encoding: "utf8", env: { ...process.env, BLENDWORKS_JOBS: "1" } });

  it("runs only the files the filters name and prints the time of each", () => {
    const result = run("test_smoke");
    expect(result.status).toBe(0);
    expect(result.stdout).toMatch(/^ok\s+test_smoke\.py\s+\d+\.\d s$/m);
    expect(result.stdout).toContain("1 of 1 bridge test files passed");
    expect(result.stdout).not.toContain("test_render");
  });

  it("fails and lists the files when a filter matches nothing", () => {
    const result = run("test_nothing");
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("no bridge test file matches test_nothing");
    expect(result.stderr).toContain("test_smoke.py");
  });

  it("refuses an unknown option", () => {
    expect(run("--bogus").status).toBe(2);
  });
});
