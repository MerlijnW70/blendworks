import { writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { findClaude, type InstallDeps, install, type InstallPlan } from "../src/mcp/install.js";
import { scratchDir } from "./mcp-helpers.js";

function deps(overrides: Partial<InstallDeps>): { deps: InstallDeps; lines: string[]; runs: InstallPlan[] } {
  const lines: string[] = [];
  const runs: InstallPlan[] = [];
  const server = join(scratchDir(), "index.js");
  writeFileSync(server, "");
  return {
    lines,
    runs,
    deps: {
      findClaude: () => "/usr/bin/claude",
      run: (plan) => (runs.push(plan), 0),
      log: (line) => lines.push(line),
      cwd: scratchDir(),
      serverPath: server,
      blender: undefined,
      ...overrides,
    },
  };
}

describe("npm run install-claude", () => {
  it("runs claude mcp add for the user with the absolute server path and workspace", () => {
    const setup = deps({});
    expect(install([], setup.deps)).toBe(0);
    expect(setup.runs).toEqual([
      {
        claude: "/usr/bin/claude",
        args: ["mcp", "add", "--scope", "user", "blendworks", "--", "node", setup.deps.serverPath, "--workspace", resolve(setup.deps.cwd, "workspace")],
      },
    ]);
  });

  it("takes --workspace and --allow-python, and passes BLENDER on", () => {
    const setup = deps({ blender: "/opt/blender/blender" });
    expect(install(["--workspace", "assets", "--allow-python"], setup.deps)).toBe(0);
    expect(setup.runs[0]?.args).toEqual([
      "mcp", "add", "--scope", "user", "-e", "BLENDER=/opt/blender/blender", "blendworks", "--",
      "node", setup.deps.serverPath, "--workspace", resolve(setup.deps.cwd, "assets"), "--allow-python",
    ]);
  });

  it("explains itself before running", () => {
    const setup = deps({});
    install([], setup.deps);
    const text = setup.lines.join("\n");
    expect(text).toContain('adds the Blendworks MCP server to Claude Code for your user, under the name "blendworks"');
    expect(text).toContain(`Imports, exports and saves stay inside ${resolve(setup.deps.cwd, "workspace")}`);
    expect(text).toContain("Running: claude mcp add --scope user blendworks -- node");
  });

  it("refuses when claude is missing, without running anything", () => {
    const setup = deps({ findClaude: () => undefined });
    expect(install([], setup.deps)).toBe(1);
    expect(setup.runs).toEqual([]);
    expect(setup.lines.join("\n")).toMatch(/^Refused: the claude command is not on PATH/);
  });

  it("refuses when the server is not built", () => {
    const setup = deps({ serverPath: join(scratchDir(), "missing.js") });
    expect(install([], setup.deps)).toBe(1);
    expect(setup.runs).toEqual([]);
    expect(setup.lines.join("\n")).toMatch(/Run npm run build first/);
  });

  it("reports a failing claude mcp add", () => {
    const setup = deps({ run: () => 1 });
    expect(install([], setup.deps)).toBe(1);
    expect(setup.lines.at(-1)).toContain("claude mcp remove --scope user blendworks");
  });
});

describe("finding claude", () => {
  it("looks on PATH", () => {
    const dir = scratchDir();
    const name = process.platform === "win32" ? "claude.cmd" : "claude";
    writeFileSync(join(dir, name), "");
    expect(findClaude({ PATH: dir })).toBe(join(dir, name));
    expect(findClaude({ PATH: scratchDir() })).toBeUndefined();
    expect(findClaude({})).toBeUndefined();
  });
});
