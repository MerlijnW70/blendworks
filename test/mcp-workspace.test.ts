import { existsSync, mkdirSync, symlinkSync } from "node:fs";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { Workspace } from "../src/mcp/workspace.js";
import { call, type Harness, headlessHarness, scratchDir, texts } from "./mcp-helpers.js";

let harness: Harness | undefined;

afterEach(async () => {
  await harness?.close();
  harness = undefined;
});

describe("the workspace", () => {
  it("is created when missing", () => {
    const dir = join(scratchDir(), "a", "b", "workspace");
    expect(existsSync(dir)).toBe(false);
    Workspace.open(dir);
    expect(existsSync(dir)).toBe(true);
  });

  it("defaults to ./workspace", async () => {
    const { parseOptions } = await import("../src/mcp/options.js");
    expect(parseOptions([]).workspace).toBe("workspace");
  });

  it("resolves client paths inside it", () => {
    const workspace = Workspace.open(scratchDir());
    expect(workspace.resolve("crate.glb")).toBe(join(workspace.root, "crate.glb"));
    expect(workspace.resolve("out/crate.glb")).toBe(join(workspace.root, "out", "crate.glb"));
    expect(workspace.resolve("out/../crate.glb")).toBe(join(workspace.root, "crate.glb"));
    expect(workspace.resolve(join(workspace.root, "crate.glb"))).toBe(join(workspace.root, "crate.glb"));
    expect(workspace.resolve("..crate.glb")).toBe(join(workspace.root, "..crate.glb"));
  });

  it.each([
    ["../crate.glb"],
    ["out/../../crate.glb"],
    [resolve("/etc/passwd")],
    [process.platform === "win32" ? "C:\\Windows\\win.ini" : "/tmp/crate.glb"],
    [""],
    ["a\0b"],
  ])("refuses %j", (path) => {
    const workspace = Workspace.open(scratchDir());
    expect(() => workspace.resolve(path)).toThrow();
  });

  it("refuses a sibling folder that shares its name as a prefix", () => {
    const base = scratchDir();
    const workspace = Workspace.open(join(base, "ws"));
    mkdirSync(join(base, "ws-other"));
    expect(() => workspace.resolve("../ws-other/crate.glb")).toThrow(/outside the workspace/);
  });

  it("refuses a path that leaves through a symbolic link", (context) => {
    const base = scratchDir();
    const workspace = Workspace.open(join(base, "ws"));
    mkdirSync(join(base, "outside"));
    try {
      symlinkSync(join(base, "outside"), join(workspace.root, "link"), "junction");
    } catch {
      context.skip("this system does not allow creating links");
    }
    expect(() => workspace.resolve("link/crate.glb")).toThrow(/outside the workspace/);
  });

  it("does not reach the bridge when a tool path escapes it", async () => {
    harness = await headlessHarness();
    const before = harness.bridge.requests.length;
    const result = await call(harness.client, "blender_export", { path: "../escape.glb" });
    expect(result.isError).toBe(true);
    expect(texts(result)).toMatch(/^Refused: "\.\.\/escape\.glb" is outside the workspace/);
    expect(harness.bridge.requests.length).toBe(before);
  });

  it("hands the bridge the absolute path inside it", async () => {
    harness = await headlessHarness();
    const result = await call(harness.client, "blender_export", { path: "crate.glb", format: "glb" });
    expect(result.isError).toBeFalsy();
    expect(harness.bridge.requests.at(-1)?.args).toEqual({ path: join(harness.started.workspace.root, "crate.glb"), format: "glb" });
  });
});
