import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { expect, it } from "vitest";
import { type Plan, runSandboxed } from "../../../src/judge/sandbox.js";
import { useBlenderSlot } from "../../setup/slot.js";

const fakeBlender = `
const fs = require("node:fs");
const [log, label, hold] = process.argv.slice(1);
fs.appendFileSync(log, "start " + label + " " + Date.now() + "\\n");
setTimeout(() => fs.appendFileSync(log, "end " + label + " " + Date.now() + "\\n"), Number(hold));
`;

export function scenario(file: string, delayMs: number, steps: { label: string; holdMs: number; gapAfterMs: number }[]): void {
  useBlenderSlot();
  it(`${file} runs ${steps.length} fake Blender processes with idle gaps between them`, async () => {
    const log = process.env["SLOT_LOG"] ?? "";
    const dir = mkdtempSync(join(tmpdir(), "blendworks-slot-file-"));
    await sleep(delayMs);
    for (const step of steps) {
      const plan: Plan = {
        command: process.execPath,
        args: ["-e", fakeBlender, log, step.label, String(step.holdMs)],
        isolation: { network: "not isolated", memory: "none", timeoutMs: 30_000, platform: "test", filesystem: "not isolated", processes: "shared PID namespace" },
        gpu: false,
        writable: [],
        lowIntegrity: false,
      };
      const run = await runSandboxed(plan, dir);
      expect(run.code).toBe(0);
      await sleep(step.gapAfterMs);
    }
  });
}
