import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ContainerCheckError, dockerArguments, imageCommit, patchOfHead, prepareInputs, resultFrom, type Run } from "../../scripts/lib/container-check.js";
import { scratch } from "./probes.js";

const BASE = "a".repeat(40);
const HEAD = "b".repeat(40);

function fakeRun(answers: Record<string, { status: number; stdout: string }>): { run: Run; calls: string[][] } {
  const calls: string[][] = [];
  const run: Run = (command, args) => {
    calls.push([command, ...args]);
    const key = [command, ...args].join(" ");
    const answer = Object.entries(answers).find(([prefix]) => key.startsWith(prefix))?.[1] ?? { status: 1, stdout: "" };
    return { status: answer.status, stdout: answer.stdout, stderr: answer.status === 0 ? "" : "refused" };
  };
  return { run, calls };
}

function resultLine(record: Record<string, unknown>): string {
  return `npm run check output\nBLENDWORKS-RESULT ${JSON.stringify(record)}\n`;
}

describe("the container check", () => {
  it("runs the image's patch entry point in Solive's sealed sandbox", () => {
    const args = dockerArguments({ image: "blendworks-judge@sha256:abc", work: "/w/work", spec: "/w/spec", patchName: "delivery.patch", patchSha256: "f".repeat(64), box: { memory: "8g", cpus: "4", tmp: "6g" }, name: "check-1" });
    const text = args.join(" ");
    for (const flag of ["--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges", "--user 65534:65534", "--pids-limit 256", "--memory 8g", "--memory-swap 8g", "--cpus 4", "--ulimit nofile=1024:1024", "--tmpfs /tmp:rw,exec,nosuid,nodev,size=6g"]) expect(text).toContain(flag);
    expect(text).toContain("type=bind,source=/w/work,target=/judge/work,readonly");
    expect(text).toContain("type=bind,source=/w/spec,target=/judge/spec,readonly");
    expect(text).toContain(`--env ARTIFACT_PATH=/judge/work/delivery.patch --env ARTIFACT_SHA256=${"f".repeat(64)}`);
    expect(args.slice(-5)).toEqual(["--entrypoint", "/bin/sh", "blendworks-judge@sha256:abc", "-c", "blendworks-judge patch"]);
  });

  it("passes only when the entry point says pass and the container exits 0", () => {
    const pass = resultLine({ verdict: "pass", reason: "npm run check passed with the patch applied", commit: BASE, details: { tail: ["ok   test"] } });
    expect(resultFrom(pass, 0)).toEqual({ verdict: "pass", exitCode: 0, reason: "npm run check passed with the patch applied", commit: BASE, tail: ["ok   test"] });
    expect(resultFrom(pass, 137)).toMatchObject({ verdict: "error", exitCode: 3 });
    expect(resultFrom(resultLine({ verdict: "fail", reason: "npm run check failed (exit 1)" }), 1)).toMatchObject({ verdict: "fail", exitCode: 1 });
    expect(resultFrom("killed\n", 137)).toMatchObject({ verdict: "error", exitCode: 137 });
    expect(resultFrom("BLENDWORKS-RESULT {not json\n", 0)).toMatchObject({ verdict: "error", exitCode: 3 });
  });

  it("checks the current commit as the diff from the image's commit to HEAD", () => {
    const { run, calls } = fakeRun({ "git rev-parse HEAD": { status: 0, stdout: `${HEAD}\n` }, "git cat-file": { status: 0, stdout: "" }, "git diff": { status: 0, stdout: "diff --git a/x b/x\n" } });
    expect(patchOfHead(BASE, run)).toBe("diff --git a/x b/x\n");
    expect(calls.at(-1)).toEqual(["git", "diff", "--binary", "--full-index", BASE, HEAD]);
  });

  it("refuses when there is nothing to apply or the image holds no commit", () => {
    expect(() => patchOfHead(BASE, fakeRun({ "git rev-parse HEAD": { status: 0, stdout: `${BASE}\n` } }).run)).toThrow(ContainerCheckError);
    expect(() => patchOfHead(BASE, fakeRun({ "git rev-parse HEAD": { status: 0, stdout: `${HEAD}\n` }, "git cat-file": { status: 1, stdout: "" } }).run)).toThrow(/not in this repository/);
    expect(() => patchOfHead(BASE, fakeRun({ "git rev-parse HEAD": { status: 0, stdout: `${HEAD}\n` }, "git cat-file": { status: 0, stdout: "" }, "git diff": { status: 0, stdout: "\n" } }).run)).toThrow(/nothing to check/);
    expect(imageCommit("img", fakeRun({ "docker image inspect": { status: 0, stdout: `${BASE}\n` } }).run)).toBe(BASE);
    expect(() => imageCommit("img", fakeRun({ "docker image inspect": { status: 0, stdout: "<no value>\n" } }).run)).toThrow(/names no commit/);
  });

  it("hands the container the patch with its sha256 and a spec", () => {
    const folder = scratch("container-check");
    const inputs = prepareInputs("diff --git a/x b/x\n", folder);
    expect(readFileSync(join(inputs.work, inputs.patchName), "utf8")).toBe("diff --git a/x b/x\n");
    expect(inputs.patchSha256).toBe(createHash("sha256").update("diff --git a/x b/x\n").digest("hex"));
    expect(readFileSync(join(inputs.spec, "SPEC.md"), "utf8")).toContain("npm run check");
  });
});
