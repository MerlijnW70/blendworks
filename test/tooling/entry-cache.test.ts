import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, inject, it } from "vitest";
import { ensureEntry, hashFiles, isComplete } from "../../scripts/lib/entry-cache.js";
import { ensureFixtures, fixtureKey, fixtureSets } from "../../scripts/lib/fixtures.js";
import { runProbe, scratch } from "./probes.js";

function counted(root: string): { counter: string; generate: () => Promise<void> } {
  const counter = join(root, "counter.txt");
  writeFileSync(counter, "");
  return {
    counter,
    generate: async () => {
      appendFileSync(counter, "generated\n");
    },
  };
}

describe("the cache key", () => {
  it("changes when a fixture script changes, when Blender changes, and not otherwise", () => {
    const folder = scratch("key");
    const script = join(folder, "fixtures.py");
    writeFileSync(script, "print(1)\n");
    const base = fixtureKey(script, "5.2.3");
    expect(fixtureKey(script, "5.2.3")).toBe(base);
    expect(fixtureKey(script, "5.2.4")).not.toBe(base);
    writeFileSync(script, "print(2)\n");
    expect(fixtureKey(script, "5.2.3")).not.toBe(base);
  });

  it("does not depend on where the checkout lives", () => {
    const one = scratch("where-a");
    const two = scratch("where-b");
    writeFileSync(join(one, "fixtures.py"), "same\n");
    writeFileSync(join(two, "fixtures.py"), "same\n");
    expect(hashFiles([join(one, "fixtures.py")])).toBe(hashFiles([join(two, "fixtures.py")]));
  });
});

describe("generating once", { timeout: 60_000 }, () => {
  it("does not regenerate on a cache hit", async () => {
    const root = scratch("hit");
    const { counter, generate } = counted(root);
    const first = await ensureEntry({ root, name: "x", key: "k1", generate });
    const second = await ensureEntry({ root, name: "x", key: "k1", generate });
    expect([first.generated, second.generated]).toEqual([true, false]);
    expect(readFileSync(counter, "utf8")).toBe("generated\n");
    expect(isComplete(first.dir)).toBe(true);
  });

  it("generates again for a new key", async () => {
    const root = scratch("newkey");
    const { counter, generate } = counted(root);
    await ensureEntry({ root, name: "x", key: "k1", generate });
    await ensureEntry({ root, name: "x", key: "k2", generate });
    expect(readFileSync(counter, "utf8")).toBe("generated\ngenerated\n");
  });

  it("generates once for two setups running at the same time in one process", async () => {
    const root = scratch("same-process");
    const { counter, generate } = counted(root);
    const [a, b] = await Promise.all([ensureEntry({ root, name: "x", key: "k", generate }), ensureEntry({ root, name: "x", key: "k", generate })]);
    expect([a.generated, b.generated].sort()).toEqual([false, true]);
    expect(readFileSync(counter, "utf8")).toBe("generated\n");
  });

  it("generates once for three setups running at the same time in separate processes", async () => {
    const root = scratch("processes");
    const counter = join(root, "counter.txt");
    writeFileSync(counter, "");
    const runs = await Promise.all([1, 2, 3].map(() => runProbe("cache-probe.ts", [root, "shared", counter])));
    for (const run of runs) expect(run, run.stderr).toMatchObject({ code: 0 });
    const generated = runs.filter((run) => (JSON.parse(run.stdout.trim().split("\n").pop() ?? "{}") as { generated: boolean }).generated);
    expect(generated).toHaveLength(1);
    expect(readFileSync(counter, "utf8")).toBe("generated\n");
  });

  it("leaves nothing behind when generation fails, and a retry generates", async () => {
    const root = scratch("failure");
    await expect(
      ensureEntry({
        root,
        name: "x",
        key: "k",
        generate: async (work) => {
          mkdirSync(join(work, "half"));
          throw new Error("boom");
        },
      }),
    ).rejects.toThrow("boom");
    const { counter, generate } = counted(root);
    const retry = await ensureEntry({ root, name: "x", key: "k", generate });
    expect(retry.generated).toBe(true);
    expect(readFileSync(counter, "utf8")).toBe("generated\n");
  });
});

describe("the judge fixtures", { timeout: 120_000 }, () => {
  it("are generated at most once: a second setup is a cache hit", async (context) => {
    if (inject("fixtureSets") === null) context.skip();
    await ensureFixtures();
    const again = await ensureFixtures();
    for (const [name, set] of Object.entries(again)) expect(set.generated, name).toBe(false);
    expect(Object.keys(again)).toEqual(fixtureSets().map((set) => set.name));
  });
});
