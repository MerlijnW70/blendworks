import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { acquireSlot, SlotWaitTimeout } from "../../scripts/lib/slots.js";
import { readTimingLog, type ProcessTiming } from "../../scripts/lib/timings.js";
import { envelopeMs, startWorkClock, WAIT_FOR_SLOT_MS, WorkTimeout } from "../setup/work-clock.js";
import { scratch } from "./probes.js";

type Assertion = { fullName: string; status: string; failureMessages: string[]; duration: number | null };
type FileReport = { name: string; status: string; message: string; assertionResults: Assertion[] };
type Nested = { code: number | null; text: string; files: FileReport[]; timings: ProcessTiming[] };

const BUDGET_MS = 1500;
const HOLD_MS = 4000;

function nested(files: string[], extra: Record<string, string>): Promise<Nested> {
  const root = scratch("work-clock");
  const report = join(root, "report.json");
  const log = join(root, "timings.jsonl");
  const env = { ...process.env, BLENDWORKS_JOBS: "1", BLENDWORKS_CACHE: root, BLENDWORKS_FIXTURES: "skip", BLENDWORKS_TIMINGS: log, BLENDWORKS_STAGE: "work-proof", ...extra };
  const args = [resolve("node_modules", "vitest", "vitest.mjs"), "run", "--config", join("test", "tooling", "work-files", "vitest.config.ts"), "--reporter=json", `--outputFile=${report}`, ...files];
  return new Promise((done, fail) => {
    const child = spawn(process.execPath, args, { env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    let text = "";
    child.stdout.on("data", (chunk: Buffer) => (text += chunk.toString()));
    child.stderr.on("data", (chunk: Buffer) => (text += chunk.toString()));
    child.on("error", fail);
    child.on("close", (code) => {
      const files = (JSON.parse(readFileSync(report, "utf8")) as { testResults: FileReport[] }).testResults;
      const timings = readTimingLog(log).filter((entry): entry is ProcessTiming => entry.kind === "process");
      done({ code, text, files, timings });
    });
  });
}

function file(run: Nested, name: string): FileReport {
  const found = run.files.find((entry) => entry.name.replace(/\\/g, "/").endsWith(`work-files/${name}`));
  if (found === undefined) throw new Error(`no result for ${name}:\n${run.text}`);
  return found;
}

function failureText(report: FileReport): string {
  return [report.message, ...report.assertionResults.flatMap((entry) => entry.failureMessages)].join("\n");
}

describe("per-test timeouts count work, never the wait for a Blender slot", { timeout: 120_000 }, () => {
  it("a test and a hook that wait for the only slot far longer than their work budget still pass", async () => {
    const run = await nested(["holder", "queued.spec", "queued-hook"], { BUDGET_MS: String(BUDGET_MS), HOLD_MS: String(HOLD_MS) });
    expect(run.code, run.text).toBe(0);
    for (const name of ["holder.spec.ts", "queued.spec.ts", "queued-hook.spec.ts"]) expect(file(run, name).status, run.text).toBe("passed");
    const waited = run.timings.filter((entry) => !entry.label.includes("holder"));
    expect(waited).toHaveLength(2);
    for (const entry of waited) {
      expect(entry.stage).toBe("work-proof");
      expect(entry.waitMs, JSON.stringify(entry)).toBeGreaterThan(BUDGET_MS);
    }
    expect(waited.map((entry) => entry.label).sort()).toEqual([
      'hook of "test/tooling/work-files/queued-hook.spec.ts"',
      'test "test/tooling/work-files/queued.spec.ts > queued > waits for the slot longer than its work budget, then works within it"',
    ]);
  });

  it("a test and a hook that hang while working fail at their budget, named, with the stage and the time working", async () => {
    const run = await nested(["hang.spec", "hang-hook"], { BUDGET_MS: "800", HOLD_MS: String(HOLD_MS) });
    expect(run.code, run.text).toBe(1);
    const test = file(run, "hang.spec.ts");
    expect(test.assertionResults[0]?.status).toBe("failed");
    expect(failureText(test)).toMatch(/timed out working, not waiting: test "test\/tooling\/work-files\/hang\.spec\.ts > hang > works past its budget" in stage work-proof worked 0\.\d s, over its work budget of 0\.8 s; it also waited \d+\.\d s for a Blender slot or a lock, which does not count/);
    expect(test.assertionResults[0]?.duration ?? HOLD_MS).toBeLessThan(HOLD_MS - 1000);
    expect(failureText(file(run, "hang-hook.spec.ts"))).toMatch(/timed out working, not waiting: hook of "test\/tooling\/work-files\/hang-hook\.spec\.ts" in stage work-proof worked 0\.\d s, over its work budget of 0\.8 s/);
  });
});

describe("the work clock", { timeout: 30_000 }, () => {
  it("stops while this process waits for a slot and runs out only on work", async () => {
    const root = scratch("work-clock-unit");
    const held = await acquireSlot({ root, jobs: 1 });
    setTimeout(() => held.release(), 700);
    const clock = startWorkClock('test "unit"', 400);
    let expired: unknown;
    clock.expired.catch((error: unknown) => (expired = error));
    const slot = await acquireSlot({ root, jobs: 1, pollMs: 5 });
    expect(slot.waitedMs).toBeGreaterThan(600);
    expect(clock.waitMs()).toBeGreaterThan(600);
    expect(clock.workMs()).toBeLessThan(200);
    expect(expired).toBeUndefined();
    slot.release();
    await new Promise((done) => setTimeout(done, 500));
    expect(expired).toBeInstanceOf(WorkTimeout);
    expect((expired as WorkTimeout).message).toMatch(/^timed out working, not waiting: test "unit" in stage \S+ worked 0\.4 s, over its work budget of 0\.4 s; it also waited 0\.[67] s/);
    clock.stop();
  });

  it("bounds waiting on its own, and says the time went to waiting", async () => {
    const root = scratch("work-clock-wait");
    const held = await acquireSlot({ root, jobs: 1 });
    const waiting = acquireSlot({ root, jobs: 1, pollMs: 5, timeoutMs: 200, label: 'test "queued"' });
    await expect(waiting).rejects.toBeInstanceOf(SlotWaitTimeout);
    await expect(waiting).rejects.toThrow(/^timed out waiting, not working: test "queued" waited 0\.2 s for one of 1 Blender slots in .* \(stage \S+\)$/);
    held.release();
  });

  it("gives vitest's own timer room for the whole wait bound on top of the work budget", () => {
    expect(envelopeMs(120_000)).toBeGreaterThan(120_000 + WAIT_FOR_SLOT_MS);
  });
});
