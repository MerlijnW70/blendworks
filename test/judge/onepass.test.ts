import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { changedStage, readProgress, stageDigest, type StageRecord } from "../../src/judge/onepass.js";
import { runSandboxed, type Plan } from "../../src/judge/sandbox.js";
import { freshDir } from "./helpers.js";

function record(stage: StageRecord["stage"], digest: string | null): StageRecord {
  return { stage, ok: true, seconds: 0.1, endedAt: 0, digest };
}

describe("the one-pass progress log", () => {
  it("reads events written with Windows or Unix line ends and skips a line cut off mid-write", () => {
    const dir = freshDir("onepass", "progress");
    const path = join(dir, "progress.log");
    writeFileSync(path, '{"event": "start", "stage": "measure", "at": 1, "seconds": null}\r\n{"event": "end", "stage": "measure", "at": 2, "seconds": 1}\n{"event": "start", "stage": "vie');
    expect(readProgress(path).map((event) => [event.event, event.stage])).toEqual([["start", "measure"], ["end", "measure"]]);
  });

  it("notices when the measurements change after the measure stage ended", () => {
    const out = freshDir("onepass", "digest");
    writeFileSync(join(out, "measurements.json"), '{"ok": true}');
    const digest = stageDigest(out, "measure");
    expect(changedStage(out, [record("measure", digest)])).toBeNull();
    writeFileSync(join(out, "measurements.json"), '{"ok": true }');
    expect(changedStage(out, [record("measure", digest)])).toMatchObject({ stage: "measure", failure: { stage: "measure", code: "changed" } });
  });

  it("covers the silhouette images of the reference stage, not only its record", () => {
    const out = freshDir("onepass", "silhouettes");
    mkdirSync(join(out, "silhouettes"), { recursive: true });
    writeFileSync(join(out, "silhouettes.json"), '{"ok": true}');
    writeFileSync(join(out, "silhouettes", "front.png"), "a");
    const digest = stageDigest(out, "reference");
    expect(changedStage(out, [record("reference", digest), record("views", "not checked")])).toBeNull();
    writeFileSync(join(out, "silhouettes", "front.png"), "b");
    expect(changedStage(out, [record("reference", digest)])).toMatchObject({ stage: "reference", failure: { stage: "reference", code: "changed" } });
  });
});

describe("the stage clock of the one judge process", () => {
  it("starts when the process starts, never while the run still waits to spawn it", async () => {
    const dir = freshDir("onepass", "clock");
    const plan: Plan = { command: process.execPath, args: ["-e", "setTimeout(() => {}, 200)"], isolation: { network: "not isolated", memory: "none", timeoutMs: 30_000, platform: "test", filesystem: "not isolated", processes: "shared PID namespace" }, gpu: false, writable: [], lowIntegrity: false };
    const seen: string[] = [];
    const result = await runSandboxed(plan, dir, {
      intervalMs: 10,
      started: () => seen.push("started"),
      check: () => {
        seen.push("check");
        return seen[0] === "started" ? "running" : "expired";
      },
    });
    expect(seen[0]).toBe("started");
    expect(seen.filter((entry) => entry === "started")).toHaveLength(1);
    expect(result.timedOut).toBe(false);
  });
});
