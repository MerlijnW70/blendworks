import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect } from "vitest";
import { type Plan, runSandboxed } from "../../../src/judge/sandbox.js";

export async function fakeBlender(holdMs: number): Promise<void> {
  const plan: Plan = {
    command: process.execPath,
    args: ["-e", `setTimeout(() => {}, ${holdMs})`],
    isolation: { network: "not isolated", memory: "none", timeoutMs: 60_000, platform: "test", filesystem: "not isolated", processes: "shared PID namespace" },
    gpu: false,
    writable: [],
    lowIntegrity: false,
  };
  const run = await runSandboxed(plan, mkdtempSync(join(tmpdir(), "blendworks-work-file-")));
  expect(run.code).toBe(0);
}
