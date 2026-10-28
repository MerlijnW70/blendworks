import { spawn, execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { blenderPath } from "../../src/blender.js";
import { SCRIPTS_DIR } from "../../src/judge/run.js";
import { blenderPython } from "../../src/judge/sandbox.js";
import { readShared, withSharedAccess } from "../../src/judge/shared-access.js";
import { freshDir } from "./helpers.js";
import { useBlenderSlot } from "../setup/slot.js";
import { withWorkBudget, workBudget } from "../setup/work-clock.js";

useBlenderSlot();

const PROBE = fileURLToPath(new URL("./shared_access_probe.py", import.meta.url));
const windows = process.platform === "win32";
type Outcome = { ok: boolean; seconds: number; error?: string };
type Probe = Record<"replace" | "create" | "read" | "append" | "plain" | "bounded", Outcome> & { bound: number };

let probe: Probe;
let python = "";

beforeAll(withWorkBudget(30_000, () => {
  if (!windows) return;
  python = blenderPython(blenderPath()) ?? "";
  const folder = freshDir("shared-access", "probe");
  execFileSync(python, ["-I", PROBE, SCRIPTS_DIR, folder], { stdio: "ignore", timeout: 25_000 });
  probe = JSON.parse(readFileSync(join(folder, "probe.json"), "utf8")) as Probe;
}));

const HOLD = `
import ctypes, sys, time
from ctypes import wintypes
k = ctypes.WinDLL("kernel32")
k.CreateFileW.restype = wintypes.HANDLE
k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
handle = k.CreateFileW(sys.argv[1], 0x80000000, 0, None, 3, 0x80, None)
print("held", flush=True)
time.sleep(float(sys.argv[2]))
print("releasing", int(time.time() * 1000), flush=True)
k.CloseHandle(handle)
`;

type Holder = { releasedAt(): Promise<number> };

function holdElsewhere(path: string, seconds: number): Promise<Holder> {
  return new Promise((held, fail) => {
    const child = spawn(python, ["-I", "-c", HOLD, path, String(seconds)], { stdio: ["ignore", "pipe", "inherit"] });
    let text = "";
    let release: (time: number) => void = () => undefined;
    const released = new Promise<number>((resolve) => {
      release = resolve;
    });
    child.on("error", fail);
    child.stdout.on("data", (chunk: Buffer) => {
      text += chunk.toString();
      if (text.includes("held")) held({ releasedAt: () => released });
      const match = /releasing (\d+)/.exec(text);
      if (match !== null) release(Number(match[1]));
    });
  });
}

describe.runIf(windows)("a judge file that another process holds for a moment, as a virus scanner does with a file just written", workBudget(60_000), () => {
  it("is not readable or writable while it is held: the race is real", () => {
    expect(probe.plain.ok).toBe(false);
    expect(probe.plain.error).toMatch(/Errno 13/);
  });

  it("is still written, replaced, read and appended to by the judge in Blender once the holder lets go", () => {
    for (const outcome of [probe.replace, probe.create, probe.read, probe.append]) {
      expect(outcome.ok).toBe(true);
      expect(outcome.seconds).toBeGreaterThan(0.2);
    }
  });

  it("fails after the bounded wait when the file stays held", () => {
    expect(probe.bounded.ok).toBe(false);
    expect(probe.bounded.seconds).toBeGreaterThanOrEqual(probe.bound);
  });

  it("is read by the judge in Node once the holder lets go", async () => {
    const path = join(freshDir("shared-access", "node"), "measurements.json");
    writeFileSync(path, "{}");
    const holder = await holdElsewhere(path, 0.3);
    expect(readShared(path).toString()).toBe("{}");
    const readAt = Date.now();
    expect(readAt).toBeGreaterThanOrEqual(await holder.releasedAt());
  });
});

describe("the bounded wait for a held file", () => {
  it("only waits on Windows, and only for a file held elsewhere", () => {
    const busy = Object.assign(new Error("busy"), { code: "EBUSY" });
    let calls = 0;
    expect(() => withSharedAccess(() => { calls += 1; throw busy; }, "linux")).toThrow("busy");
    expect(calls).toBe(1);
    const missing = Object.assign(new Error("missing"), { code: "ENOENT" });
    expect(() => withSharedAccess(() => { calls += 1; throw missing; }, "win32")).toThrow("missing");
    expect(calls).toBe(2);
  });
});
