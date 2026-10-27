import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { findClaude, type InstallDeps, install, type InstallPlan, planInstall, runClaude } from "../src/mcp/install.js";
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
        args: ["mcp", "add", "blendworks", "--scope", "user", "--", "node", setup.deps.serverPath, "--workspace", resolve(setup.deps.cwd, "workspace")],
      },
    ]);
  });

  it("takes --workspace and --allow-python, and passes BLENDER on", () => {
    const setup = deps({ blender: "/opt/blender/blender" });
    expect(install(["--workspace", "assets", "--allow-python"], setup.deps)).toBe(0);
    expect(setup.runs[0]?.args).toEqual([
      "mcp", "add", "blendworks", "--scope", "user", "--env=BLENDER=/opt/blender/blender", "--",
      "node", setup.deps.serverPath, "--workspace", resolve(setup.deps.cwd, "assets"), "--allow-python",
    ]);
  });

  it("attaches BLENDER to a single --env= argument so the variadic option cannot consume the server command", () => {
    for (const blender of [undefined, "/opt/blender/blender", "C:\Program Files\Blender 5\blender.exe"]) {
      const setup = deps({ blender });
      install([], setup.deps);
      const args = setup.runs[0]?.args ?? [];
      expect(args.slice(0, 3)).toEqual(["mcp", "add", "blendworks"]);
      const separator = args.indexOf("--");
      expect(separator).toBeGreaterThan(2);
      expect(args.filter((arg) => arg === "-e" || arg === "--env")).toEqual([]);
      expect(args.slice(3, separator).filter((arg) => arg.startsWith("--env="))).toEqual(blender === undefined ? [] : [`--env=BLENDER=${blender}`]);
      expect(args.slice(separator + 1, separator + 3)).toEqual(["node", setup.deps.serverPath]);
    }
  });

  it("explains itself before running", () => {
    const setup = deps({});
    install([], setup.deps);
    const text = setup.lines.join("\n");
    expect(text).toContain('adds the Blendworks MCP server to Claude Code for your user, under the name "blendworks"');
    expect(text).toContain(`Imports, exports and saves stay inside ${resolve(setup.deps.cwd, "workspace")}`);
    expect(text).toContain("Running: claude mcp add blendworks --scope user -- node");
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

function mcpEntriesFingerprint(path: string): string {
  if (!existsSync(path)) return "absent";
  const config = JSON.parse(readFileSync(path, "utf8")) as { mcpServers?: unknown; projects?: Record<string, { mcpServers?: unknown }> };
  const projects = Object.entries(config.projects ?? {}).map(([project, entry]) => [project, entry.mcpServers ?? null]);
  return createHash("sha256").update(JSON.stringify([config.mcpServers ?? null, projects])).digest("hex");
}

const realClaude = findClaude();

describe("registering with the real claude binary", () => {
  it.skipIf(realClaude === undefined)("registers name, command, arguments and BLENDER into a temporary configuration", () => {
    const home = scratchDir();
    const config = join(home, "config");
    mkdirSync(config, { recursive: true });
    const isolated: NodeJS.ProcessEnv = {
      ...process.env,
      HOME: home,
      USERPROFILE: home,
      APPDATA: join(home, "appdata"),
      LOCALAPPDATA: join(home, "localappdata"),
      XDG_CONFIG_HOME: join(home, "xdg"),
      CLAUDE_CONFIG_DIR: config,
    };
    const realConfig = join(homedir(), ".claude.json");
    const before = mcpEntriesFingerprint(realConfig);
    const server = join(home, "mcp server", "index.js");
    mkdirSync(join(home, "mcp server"));
    writeFileSync(server, "");
    const blender = join(home, "Blender 5", "blender.exe");
    const plan = planInstall({ claude: realClaude ?? "", serverPath: server, workspace: join(home, "work space"), allowPython: true, blender });
    expect(runClaude(plan, isolated)).toBe(0);
    const entry = JSON.parse(readFileSync(join(config, ".claude.json"), "utf8")).mcpServers.blendworks;
    expect(entry.command).toBe("node");
    expect(entry.args).toEqual([server, "--workspace", join(home, "work space"), "--allow-python"]);
    expect(entry.env).toEqual({ BLENDER: blender });
    const shown = spawnSync(realClaude ?? "", ["mcp", "get", "blendworks"], { env: isolated, encoding: "utf8", shell: /\.(cmd|bat)$/i.test(realClaude ?? "") });
    expect(shown.stdout).toContain("blendworks:");
    expect(shown.stdout).toContain(`BLENDER=${blender}`);
    expect(mcpEntriesFingerprint(realConfig)).toBe(before);
  }, 60_000);
});
