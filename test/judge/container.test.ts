import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, posix } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { parseResult, type EntryResult } from "../../src/judge/container/result.js";
import { BOX, DIGESTED, JOB_DEFAULTS, RETRY_EXIT, soliveDockerArgs } from "../../scripts/lib/judge-command.js";
import { buildJudgeImage, type ImageRecord } from "../../scripts/lib/judge-image.js";
import { CRATE_SPEC, makeFixtures } from "./helpers.js";
import { useBlenderSlot, whileProcessRunsSync } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const DOCKER = spawnSync("docker", ["version", "--format", "{{.Server.Version}}"], { encoding: "utf8", timeout: 30_000, windowsHide: true }).status === 0;
const SECRET = `planted beside the work folder ${process.pid}`;

let record: ImageRecord;
let fixtures = "";
let base = "";

type Ran = { code: number | null; output: string; result: EntryResult | null };

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function job(name: string, files: Record<string, string | Buffer>, spec = "# Job\n"): { work: string; spec: string; artifact: string; sha: string } {
  const folder = join(base, name);
  mkdirSync(join(folder, "work"), { recursive: true });
  mkdirSync(join(folder, "spec"), { recursive: true });
  writeFileSync(join(folder, "spec", "SPEC.md"), spec);
  writeFileSync(join(folder, "secret.txt"), SECRET);
  for (const [file, data] of Object.entries(files)) writeFileSync(join(folder, "work", file), data);
  const first = Object.keys(files)[0]!;
  return { work: join(folder, "work"), spec: join(folder, "spec"), artifact: posix.join("/judge/work", first), sha: sha256(join(folder, "work", first)) };
}

function inContainer(run: string, made: ReturnType<typeof job>, extra: string[] = [], network = "none"): Ran {
  const args = soliveDockerArgs({ image: record.image, run, work: made.work, spec: made.spec, artifact: made.artifact, artifactSha256: made.sha, ...BOX });
  args[args.indexOf("--network") + 1] = network;
  const at = args.indexOf("--entrypoint");
  const docker = spawnSync("docker", [...args.slice(0, 1), "--rm", ...extra, ...args.slice(1, at), ...args.slice(at)], { encoding: "utf8", timeout: 20 * 60_000, windowsHide: true, maxBuffer: 64 * 1024 * 1024 });
  const output = `${docker.stdout ?? ""}${docker.stderr ?? ""}`;
  return { code: docker.status, output, result: parseResult(docker.stdout ?? "") };
}

function replaceFile(path: string, before: string, after: string): string {
  const old = before.endsWith("\n") ? before.slice(0, -1).split("\n") : before.split("\n");
  const fresh = after.endsWith("\n") ? after.slice(0, -1).split("\n") : after.split("\n");
  return [`diff --git a/${path} b/${path}`, `--- a/${path}`, `+++ b/${path}`, `@@ -1,${old.length} +1,${fresh.length} @@`, ...old.map((line) => `-${line}`), ...fresh.map((line) => `+${line}`), ""].join("\n");
}

function checkScript(): string {
  return spawnSync("git", ["show", `${record.commit}:scripts/check.mjs`], { encoding: "utf8" }).stdout;
}

const HOSTILE_CHECK = (hostSecret: string) => `import { existsSync, readdirSync, readFileSync } from "node:fs";
const tried = {};
for (const path of [${JSON.stringify(hostSecret)}, "/judge/secret.txt", "/judge/work/../secret.txt", "/proc/1/root/judge/secret.txt"]) {
  try { tried[path] = readFileSync(path, "utf8"); } catch (error) { tried[path] = "refused " + error.code; }
}
let network = "unreachable";
try { await fetch("https://registry.npmjs.org/", { signal: AbortSignal.timeout(3000) }); network = "reached"; } catch (error) { network = "unreachable " + (error.cause?.code ?? error.name); }
console.log("HOSTILE " + JSON.stringify({ tried, network, judge: readdirSync("/judge"), mounted: existsSync("/mnt/c") || existsSync("/mnt/f") }));
`;

describe.skipIf(!DOCKER)("the judge image under Solive's docker sandbox", workBudget(60 * 60_000), () => {
  beforeAll(withWorkBudget(45 * 60_000, async () => {
    record = await buildJudgeImage({ commit: "HEAD", log: () => undefined });
    ({ assets: fixtures } = makeFixtures("container"));
    base = mkdtempSync(join(tmpdir(), "blendworks-container-"));
  }));

  afterAll(() => {
    if (base !== "") rmSync(base, { recursive: true, force: true });
  });

  it("is named by its digest, runs as a non-root user and writes only to its work folder", () => {
    expect(record.image).toMatch(DIGESTED);
    const inspected = JSON.parse(spawnSync("docker", ["image", "inspect", record.image], { encoding: "utf8" }).stdout)[0];
    expect(inspected.Config.User).toBe("65534:65534");
    expect(inspected.Config.Volumes ?? {}).toEqual({});
    expect(inspected.Config.Labels["org.blendworks.commit"]).toBe(record.commit);
    expect(inspected.Config.Env).toContain("BLENDWORKS_DEVICE=cpu");
  });

  it("sees no network and none of the host's folders from inside, and can write only its work folders", () => {
    const made = job("probe", { "asset.glb": "glb" });
    const ran = inContainer(`blendworks-judge probe --try /judge/secret.txt --try ${JSON.stringify(join(base, "probe", "secret.txt"))}`, made);
    expect(ran.result?.verdict, ran.output.slice(-2000)).toBe("pass");
    const details = ran.result!.details as { network: { reached: boolean }[]; writes: Record<string, string>; host: Record<string, string> };
    expect(details.network.every((entry) => !entry.reached)).toBe(true);
    expect(details.writes["/judge/work"]).toMatch(/^refused/);
    expect(details.writes["/"]).toMatch(/^refused/);
    expect(details.writes["/tmp/blendworks"]).toBe("writable");
    expect(details.writes["/opt/blendworks"]).toMatch(/^refused/);
    expect(Object.values(details.host).every((state) => state === "absent")).toBe(true);
    expect(ran.output).not.toContain(SECRET);
  });

  it("judges an asset with blendworks judge: a pass exits 0, a fail exits 1", () => {
    const spec = `# Crate\n\n\`\`\`json\n${JSON.stringify({ ...CRATE_SPEC, views: ["front"] }, null, 2)}\n\`\`\`\n`;
    const passed = whileProcessRunsSync(() => inContainer(JOB_DEFAULTS.asset.run, job("crate", { "crate.glb": readFileSync(join(fixtures, "crate.glb")) }, spec)));
    expect(passed.code, passed.output.slice(-3000)).toBe(0);
    expect(passed.result).toMatchObject({ kind: "asset", verdict: "pass", commit: record.commit });
    expect(passed.result?.isolation).toContain("no network, read-only root");
    expect(passed.output).toContain("isolation: container");
    const failed = whileProcessRunsSync(() => inContainer(JOB_DEFAULTS.asset.run, job("wrong", { "crate.glb": readFileSync(join(fixtures, "wrong-size.glb")) }, spec)));
    expect(failed.code).toBe(1);
    expect(failed.result).toMatchObject({ verdict: "fail", details: { failedRules: ["size.x"] } });
  });

  it("refuses work outside its input folder and refuses to run outside a sealed container", () => {
    const made = job("outside", { "crate.glb": "glb" }, "```json\n{}\n```\n");
    for (const path of ["/etc/passwd", "/judge/secret.txt", "/opt/blendworks/package.json"]) {
      const ran = inContainer(`blendworks-judge asset --artifact ${path}`, made);
      expect(ran.code, path).toBe(RETRY_EXIT);
      expect(ran.result?.verdict).toBe("error");
    }
    const open = inContainer(JOB_DEFAULTS.asset.run, made, [], "bridge");
    expect(open.code).toBe(RETRY_EXIT);
    expect(open.result?.reason).toContain("refuses to run outside a sealed container");
  });

  it("applies a patch to the image's commit and runs npm run check: exit 0 on pass, 1 on fail", () => {
    const before = checkScript();
    const passing = inContainer(JOB_DEFAULTS.code.run, job("patch-pass", { "delivery.patch": replaceFile("scripts/check.mjs", before, 'console.log("checked");\nprocess.exitCode = 0;\n') }));
    expect(passing.code, passing.output.slice(-3000)).toBe(0);
    expect(passing.result).toMatchObject({ kind: "patch", verdict: "pass", details: { paths: ["scripts/check.mjs"] } });
    const failing = inContainer(JOB_DEFAULTS.code.run, job("patch-fail", { "delivery.patch": replaceFile("scripts/check.mjs", before, "process.exitCode = 1;\n") }));
    expect(failing.code).toBe(1);
    expect(failing.result?.verdict).toBe("fail");
  });

  it("gives a hostile patch no file planted outside its folder and no network", () => {
    const hostSecret = join(base, "hostile", "secret.txt");
    const ran = inContainer(JOB_DEFAULTS.code.run, job("hostile", { "delivery.patch": replaceFile("scripts/check.mjs", checkScript(), HOSTILE_CHECK(hostSecret)) }));
    expect(ran.code, ran.output.slice(-3000)).toBe(0);
    const line = ran.output.split("\n").find((entry) => entry.startsWith("HOSTILE "));
    const seen = JSON.parse(line!.slice("HOSTILE ".length)) as { tried: Record<string, string>; network: string; judge: string[]; mounted: boolean };
    expect(Object.values(seen.tried).every((value) => value.startsWith("refused"))).toBe(true);
    expect(seen.network).toMatch(/^unreachable/);
    expect(seen.judge.sort()).toEqual(["spec", "work"]);
    expect(seen.mounted).toBe(false);
    expect(ran.output).not.toContain(SECRET);
  });

  it("refuses a patch that reaches outside the repository or adds a link", () => {
    const escape = "diff --git a/../outside.txt b/../outside.txt\nnew file mode 100644\n--- /dev/null\n+++ b/../outside.txt\n@@ -0,0 +1 @@\n+planted\n";
    const link = "diff --git a/link b/link\nnew file mode 120000\n--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+/judge\n";
    const gitConfig = "diff --git a/.git/hooks/pre-commit b/.git/hooks/pre-commit\nnew file mode 100755\n--- /dev/null\n+++ b/.git/hooks/pre-commit\n@@ -0,0 +1 @@\n+echo planted\n";
    for (const [name, patch] of [["escape", escape], ["link", link], ["git", gitConfig]] as const) {
      const ran = inContainer(JOB_DEFAULTS.code.run, job(`patch-${name}`, { "delivery.patch": patch }));
      expect(ran.code, name).toBe(1);
      expect(ran.result?.reason, name).toContain("outside the repository");
    }
  });

  it("builds the same digest again from the same commit, without any cache", async () => {
    const again = await buildJudgeImage({ commit: record.commit, noCache: true, log: () => undefined });
    expect(again.digest).toBe(record.digest);
  });
});

describe.runIf(!DOCKER)("the judge image", () => {
  it.skip("needs Docker: start Docker to build the image and run the container tests", () => undefined);
});
