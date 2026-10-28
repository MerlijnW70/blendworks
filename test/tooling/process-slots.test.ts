import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { type Plan, runSandboxed } from "../../src/judge/sandbox.js";
import { startSession } from "../../src/session.js";
import { acquireSlot, activeSlots } from "../../scripts/lib/slots.js";
import { cacheRoot } from "../../scripts/lib/paths.js";
import { FAKE_BLENDER } from "../setup/fake-blender.js";
import { intervals, maxOverlap, scratch } from "./probes.js";

const LIST_SLOTS = `
const fs = require("node:fs");
const dir = require("node:path").join(process.argv[1], "slots");
process.stdout.write(String(fs.existsSync(dir) ? fs.readdirSync(dir).filter((name) => /^slot-\\d+\\.lock$/.test(name)).length : 0));
`;


const saved = { cache: process.env["BLENDWORKS_CACHE"], jobs: process.env["BLENDWORKS_JOBS"] };
let root = "";

beforeEach(() => {
  root = scratch("process-slots");
  process.env["BLENDWORKS_CACHE"] = root;
  process.env["BLENDWORKS_JOBS"] = "1";
});

afterEach(() => {
  for (const [name, value] of [["BLENDWORKS_CACHE", saved.cache], ["BLENDWORKS_JOBS", saved.jobs]] as const) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
});

const FAKE_FOLDER = join(cacheRoot(), "fake-blender");

function fakeBlender(): string {
  const folder = FAKE_FOLDER;
  mkdirSync(folder, { recursive: true });
  if (process.platform === "win32") {
    const path = join(folder, "blender.exe");
    if (!existsSync(path)) copyFileSync(process.execPath, path);
    return path;
  }
  const path = join(folder, "blender");
  writeFileSync(path, `#!/bin/sh\nexec "${process.execPath}" "$@"\n`, { mode: 0o755 });
  return path;
}

function plan(args: string[]): Plan {
  return { command: process.execPath, args, isolation: { network: "not isolated", memory: "none", timeoutMs: 30_000, platform: "test", filesystem: "not isolated", processes: "shared PID namespace" }, gpu: false, writable: [], lowIntegrity: false };
}

describe("Blender slots are held per process", { timeout: 60_000 }, () => {
  it("runSandboxed holds a slot while its process runs and none before or after", async () => {
    expect(activeSlots(root)).toEqual([]);
    const during = await runSandboxed(plan(["-e", LIST_SLOTS, root]), root);
    expect(during.output).toBe("1");
    expect(activeSlots(root)).toEqual([]);
    const second = await runSandboxed(plan(["-e", LIST_SLOTS, root]), root);
    expect(second.output).toBe("1");
    expect(activeSlots(root)).toEqual([]);
  });

  it("runSandboxed lets two callers of one file run one after the other with one slot", async () => {
    const log = join(root, "log.txt");
    writeFileSync(log, "");
    await Promise.all(["x", "y", "z"].map((label) => runSandboxed(plan(["-e", FAKE_BLENDER, log, label, "250"]), root)));
    const seen = intervals(log);
    expect(seen).toHaveLength(3);
    expect(maxOverlap(seen)).toBe(1);
  });

  it("execFileSync of a Blender binary holds a slot for the call, and other programs hold none", () => {
    const blender = fakeBlender();
    expect(execFileSync(blender, ["-e", LIST_SLOTS, root], { encoding: "utf8" })).toBe("1");
    expect(activeSlots(root)).toEqual([]);
    expect(execFileSync(process.execPath, ["-e", LIST_SLOTS, root], { encoding: "utf8" })).toBe("0");
  });

  it("a stdio server that starts Blender holds a slot from start to close", async () => {
    const serve = ["-e", "setInterval(() => {}, 1000)"];
    const environment = Object.fromEntries(Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined && entry[0] !== "BLENDER"));
    const withoutBlender = new StdioClientTransport({ command: process.execPath, args: serve, env: environment });
    await withoutBlender.start();
    expect(activeSlots(root)).toEqual([]);
    await withoutBlender.close();
    const withBlender = new StdioClientTransport({ command: process.execPath, args: serve, env: { ...environment, BLENDER: fakeBlender() } });
    await withBlender.start();
    expect(activeSlots(root)).toHaveLength(1);
    await withBlender.close();
    expect(activeSlots(root)).toEqual([]);
  });

  it("startSession waits for a slot before it spawns, and frees it when Blender cannot start or exits", async () => {
    const taken = await acquireSlot({ root });
    let started = false;
    const pending = startSession({ blender: fakeBlender(), workspace: root }).then((session) => {
      started = true;
      return session;
    });
    await new Promise((done) => setTimeout(done, 400));
    expect(started).toBe(false);
    taken.release();
    const session = await pending;
    await session.exited;
    await vacated();
    await expect(startSession({ blender: join(root, "missing-blender"), workspace: root })).rejects.toThrow(/could not start Blender/);
    expect(activeSlots(root)).toEqual([]);
  });
});

async function vacated(): Promise<void> {
  const deadline = Date.now() + 5000;
  while (activeSlots(root).length > 0 && Date.now() < deadline) await new Promise((done) => setTimeout(done, 20));
  expect(activeSlots(root)).toEqual([]);
}

describe("Blender slots across test files", { timeout: 120_000 }, () => {
  it("with BLENDWORKS_JOBS=1 never overlap, and a file between two processes does not block another file", async () => {
    const log = join(root, "files.txt");
    writeFileSync(log, "");
    const env = { ...process.env, BLENDWORKS_JOBS: "1", BLENDWORKS_CACHE: root, SLOT_LOG: log, BLENDWORKS_FIXTURES: "skip" };
    const output = await new Promise<{ code: number | null; text: string }>((done, fail) => {
      const child = spawn(process.execPath, [resolve("node_modules", "vitest", "vitest.mjs"), "run", "--config", join("test", "tooling", "slot-files", "vitest.config.ts")], { env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
      let text = "";
      child.stdout.on("data", (chunk: Buffer) => (text += chunk.toString()));
      child.stderr.on("data", (chunk: Buffer) => (text += chunk.toString()));
      child.on("error", fail);
      child.on("close", (code) => done({ code, text }));
    });
    expect(output, output.text).toMatchObject({ code: 0 });
    const seen = intervals(log);
    expect(seen.map((item) => item.label).sort()).toEqual(["a1", "a2", "b1"]);
    expect(maxOverlap(seen)).toBe(1);
    const at = (label: string) => seen.find((item) => item.label === label) as { start: number; end: number };
    expect(at("b1").start).toBeGreaterThanOrEqual(at("a1").end);
    expect(at("b1").start).toBeLessThan(at("a2").start);
    expect(at("b1").end).toBeLessThanOrEqual(at("a2").start);
  });
});
