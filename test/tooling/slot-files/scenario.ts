import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import { type Plan, runSandboxed } from "../../../src/judge/sandbox.js";
import { FAKE_BLENDER } from "../../setup/fake-blender.js";
import { useBlenderSlot } from "../../setup/slot.js";
import { waitFor } from "../../setup/wait-for.js";

function logged(log: string, line: string): boolean {
  return existsSync(log) && readFileSync(log, "utf8").split("\n").some((entry) => entry.startsWith(`${line} `));
}

export function scenario(file: string, steps: { label: string; holdMs: number; after?: string }[]): void {
  useBlenderSlot();
  it(`${file} runs ${steps.length} fake Blender processes, each after the event it waits for, holding no slot while it waits`, async () => {
    const log = process.env["SLOT_LOG"] ?? "";
    const dir = mkdtempSync(join(tmpdir(), "blendworks-slot-file-"));
    for (const step of steps) {
      if (step.after !== undefined) await waitFor(() => logged(log, step.after as string), { description: `"${step.after}" in the slot log` });
      const plan: Plan = {
        command: process.execPath,
        args: ["-e", FAKE_BLENDER, log, step.label, String(step.holdMs)],
        isolation: { network: "not isolated", memory: "none", timeoutMs: 30_000, platform: "test", filesystem: "not isolated", processes: "shared PID namespace" },
        gpu: false,
        writable: [],
        lowIntegrity: false,
      };
      const run = await runSandboxed(plan, dir);
      expect(run.code).toBe(0);
    }
  });
}
