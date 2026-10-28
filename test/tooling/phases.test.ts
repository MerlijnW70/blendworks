import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { fastPhases, fullPhases } from "../../scripts/lib/checks.js";
import { runPhases, type Step } from "../../scripts/lib/pipeline.js";
import { repoRoot } from "../../scripts/lib/paths.js";
import { waitFor } from "../setup/wait-for.js";
import { scratch } from "./probes.js";

function listFiles(folder: string, prefix = "test/"): string[] {
  return readdirSync(folder).flatMap((name) => (statSync(join(folder, name)).isDirectory() ? listFiles(join(folder, name), `${prefix}${name}/`) : [`${prefix}${name}`]));
}

const DIST_PATH = /(^|[^\w])dist[\\/]/;

function node(name: string, source: string): Step {
  return { name, command: process.execPath, args: ["-e", source] };
}

describe("the phases of the full check", () => {
  it("run the rules, the typecheck, the build and the add-on build beside the tests, in one phase", () => {
    const phases = fullPhases();
    expect(phases).toHaveLength(1);
    expect((phases[0] ?? []).map((step) => step.name).sort()).toEqual(["build", "build:addon", "rules", "test", "test:bridge", "typecheck"]);
  });

  it("run the quick checks of check:fast beside its tests, in one phase", () => {
    const phases = fastPhases(["test/a.test.ts"], ["test_a.py"], true);
    expect(phases).toHaveLength(1);
    expect((phases[0] ?? []).map((step) => step.name)).toEqual(["rules", "typecheck", "test test/a.test.ts", "test:bridge test_a.py"]);
  });

  it("need no build output: no test reads dist, and the add-on test builds its own archive", () => {
    const own = "test/tooling/phases.test.ts";
    const tests = [...readdirSync(join(repoRoot, "bridge", "tests")).map((name) => `bridge/tests/${name}`), ...listFiles(join(repoRoot, "test")).filter((file) => file !== own)];
    expect(tests.length).toBeGreaterThan(100);
    for (const file of tests) if (/\.(ts|py)$/.test(file)) expect(readFileSync(join(repoRoot, file), "utf8"), file).not.toMatch(DIST_PATH);
    expect(readFileSync(join(repoRoot, "bridge/tests/test_addon.py"), "utf8")).toContain("build_addon.build(");
  });
});

describe("running steps side by side", () => {
  it("stops the others as soon as one fails, and reports them as stopped", { timeout: 60_000 }, async () => {
    const marker = join(scratch("fail-fast"), "finished.txt");
    const sleeper = `const fs = require("node:fs"); setTimeout(() => fs.writeFileSync(${JSON.stringify(marker)}, "done"), 15000);`;
    const result = await runPhases([[node("slow", sleeper), node("broken", "process.exit(3)")], [node("never", `require("node:fs").writeFileSync(${JSON.stringify(marker)}, "later")`)]]);
    expect(result.passed).toBe(false);
    const byName = Object.fromEntries(result.results.map((entry) => [entry.name, entry]));
    expect(byName["broken"]?.passed).toBe(false);
    expect(byName["slow"]?.cancelled).toBe(true);
    expect(byName["never"]).toBeUndefined();
    await new Promise((done) => setTimeout(done, 100));
    expect(existsSync(marker)).toBe(false);
  });

  it("lets every step finish when none fails", { timeout: 60_000 }, async () => {
    const folder = scratch("all-pass");
    const steps = ["a", "b", "c"].map((name) => node(name, `require("node:fs").writeFileSync(${JSON.stringify(join(folder, name))}, "x")`));
    const result = await runPhases([steps]);
    expect(result.passed).toBe(true);
    await waitFor(() => ["a", "b", "c"].every((name) => existsSync(join(folder, name))), { description: "all three steps" });
  });
});
