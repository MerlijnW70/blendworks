import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { failingFiles, parseWatchArgs, watch, type WatchOptions } from "../../scripts/lib/watch.js";
import { scratch } from "./probes.js";

const CHECK = `import { readFileSync } from "node:fs";
const good = readFileSync("state.txt", "utf8").trim() === "good";
console.log(good ? "ok   [test] test/a.test.ts 0.1 s" : "FAIL [test] test/a.test.ts 0.1 s");
console.log(good ? "ok   test_b.py                    0.2 s" : "FAIL test_b.py                    0.2 s");
console.log(good ? "passed in 0:01" : "FAILED in 0:01 (test 1 s)");
process.exitCode = good ? 0 : 1;
`;

function git(cwd: string, ...args: string[]): string {
  return execFileSync("git", ["-c", "user.email=watch@example.invalid", "-c", "user.name=watch", ...args], { cwd, encoding: "utf8" }).trim();
}

function fixture(): string {
  const repo = scratch("watch-repo");
  git(repo, "init", "--quiet", "--initial-branch=main");
  writeFileSync(join(repo, "package.json"), JSON.stringify({ name: "watched", private: true, scripts: { check: "node check.mjs" } }));
  writeFileSync(join(repo, "check.mjs"), CHECK);
  writeFileSync(join(repo, "state.txt"), "good\n");
  git(repo, "add", "-A");
  git(repo, "commit", "--quiet", "-m", "a passing commit");
  return repo;
}

function snapshot(repo: string): string {
  return [git(repo, "status", "--porcelain", "--ignored"), git(repo, "for-each-ref"), git(repo, "rev-parse", "HEAD"), git(repo, "stash", "list")].join("\n");
}

describe("check:watch", () => {
  it("checks each new main commit once and writes a result file and a status line: pass, or the failing files and their tail", async () => {
    const repo = fixture();
    const out = scratch("watch-out");
    const options: WatchOptions = { repo, branch: "main", out, intervalMs: 1000, once: true, command: ["npm", "run", "check"], idleSlots: undefined };
    const before = snapshot(repo);
    const [passed] = await watch(options, async () => undefined, () => undefined);
    expect(passed?.passed).toBe(true);
    expect(await watch(options, async () => undefined, () => undefined)).toEqual([]);
    writeFileSync(join(repo, "state.txt"), "bad\n");
    git(repo, "commit", "--quiet", "-am", "a failing commit");
    const changed = snapshot(repo);
    const [failed] = await watch(options, async () => undefined, () => undefined);
    expect(failed?.passed).toBe(false);
    expect(failed?.failing).toEqual(["test/a.test.ts", "test_b.py"]);
    expect(failed?.tail.at(-1)).toContain("FAILED in 0:01");
    const status = readFileSync(join(out, "status.log"), "utf8").trim().split("\n");
    expect(status).toHaveLength(2);
    expect(status[0]).toMatch(new RegExp(`${passed?.commit.slice(0, 12)} pass \\d+:\\d\\d a passing commit$`));
    expect(status[1]).toMatch(new RegExp(`${failed?.commit.slice(0, 12)} FAIL \\d+:\\d\\d test/a.test.ts, test_b.py: .*FAILED in 0:01`));
    for (const result of [passed, failed]) expect(JSON.parse(readFileSync(join(out, "results", `${result?.commit}.json`), "utf8")).passed).toBe(result?.passed);
    expect(existsSync(failed?.log ?? "")).toBe(true);
    expect(snapshot(repo)).not.toBe(before);
    expect(snapshot(repo)).toBe(changed);
  }, 120_000);

  it("names failing files from the progress lines of vitest and the bridge runner", () => {
    expect(failingFiles("ok   [test] test/x.test.ts 1 s\nFAIL [test] test/y.test.ts 2 s\nstop [test:bridge] bridge/tests/test_z.py 3 s\nFAIL test_w.py   1.0 s\n")).toEqual(["test/y.test.ts", "bridge/tests/test_z.py", "test_w.py"]);
  });

  it("refuses unknown arguments and an interval that is not whole seconds", () => {
    expect(parseWatchArgs(["--nope"])).toMatch(/unknown argument --nope/);
    expect(parseWatchArgs(["--interval", "0.5"])).toMatch(/whole seconds/);
    expect(parseWatchArgs(["--once", "--interval", "30"])).toMatchObject({ once: true, intervalMs: 30_000, branch: "main" });
  });
});
