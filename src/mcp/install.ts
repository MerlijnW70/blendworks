import { spawnSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { DEFAULT_WORKSPACE } from "./workspace.js";

export const MCP_NAME = "blendworks";

export interface InstallPlan {
  claude: string;
  args: string[];
}

export interface InstallInput {
  claude: string;
  serverPath: string;
  workspace: string;
  allowPython: boolean;
  blender: string | undefined;
}

export function findClaude(env: NodeJS.ProcessEnv = process.env, platform: NodeJS.Platform = process.platform): string | undefined {
  const names = platform === "win32" ? ["claude.exe", "claude.cmd", "claude.bat"] : ["claude"];
  const path = env["PATH"] ?? env["Path"] ?? "";
  for (const dir of path.split(platform === "win32" ? ";" : delimiter)) {
    if (dir === "") continue;
    for (const name of names) {
      const candidate = join(dir, name);
      if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
    }
  }
  return undefined;
}

export function planInstall(input: InstallInput): InstallPlan {
  const env = input.blender === undefined ? [] : ["-e", `BLENDER=${input.blender}`];
  const serverArgs = ["--workspace", input.workspace, ...(input.allowPython ? ["--allow-python"] : [])];
  return { claude: input.claude, args: ["mcp", "add", "--scope", "user", ...env, MCP_NAME, "--", "node", input.serverPath, ...serverArgs] };
}

export function explain(plan: InstallPlan, input: InstallInput): string {
  return [
    `This adds the Blendworks MCP server to Claude Code for your user, under the name "${MCP_NAME}".`,
    `Claude Code will start it as: node ${input.serverPath} --workspace ${input.workspace}${input.allowPython ? " --allow-python" : ""}`,
    `It uses a desktop Blender add-on on 127.0.0.1:${process.env["BLENDWORKS_PORT"] ?? "9876"} when one answers, and otherwise starts a headless Blender (${input.blender ?? "the default path, or set BLENDER"}).`,
    `Imports, exports and saves stay inside ${input.workspace}.`,
    input.allowPython ? "run_python is enabled: the agent can run arbitrary Python code inside Blender." : "run_python stays off; pass --allow-python to enable it.",
    `Running: claude ${plan.args.join(" ")}`,
  ].join("\n");
}

const CMD_SPECIAL = ['"', "%", "^", "&", "|", "<", ">", "!", "\r", "\n"];

function quoteForCmd(arg: string): string {
  if (CMD_SPECIAL.some((special) => arg.includes(special))) throw new Error(`cannot pass ${JSON.stringify(arg)} safely through cmd.exe; use a path without quotes or special characters`);
  return `"${arg}"`;
}

export function runClaude(plan: InstallPlan): number {
  const isScript = /\.(cmd|bat)$/i.test(plan.claude);
  const outcome = isScript
    ? spawnSync([plan.claude, ...plan.args].map(quoteForCmd).join(" "), { stdio: "inherit", shell: true })
    : spawnSync(plan.claude, plan.args, { stdio: "inherit" });
  if (outcome.error !== undefined) throw outcome.error;
  return outcome.status ?? 1;
}

export interface InstallDeps {
  findClaude: () => string | undefined;
  run: (plan: InstallPlan) => number;
  log: (line: string) => void;
  cwd: string;
  serverPath: string;
  blender: string | undefined;
}

export function install(argv: string[], deps: InstallDeps): number {
  const { values } = parseArgs({
    args: argv,
    options: { workspace: { type: "string" }, "allow-python": { type: "boolean" } },
    strict: true,
    allowPositionals: false,
  });
  const claude = deps.findClaude();
  if (claude === undefined) {
    deps.log("Refused: the claude command is not on PATH. Install Claude Code first (https://docs.claude.com/en/docs/claude-code), then run npm run install-claude again.");
    return 1;
  }
  if (!existsSync(deps.serverPath)) {
    deps.log(`Refused: ${deps.serverPath} does not exist. Run npm run build first.`);
    return 1;
  }
  const input: InstallInput = {
    claude,
    serverPath: deps.serverPath,
    workspace: resolve(deps.cwd, values.workspace ?? DEFAULT_WORKSPACE),
    allowPython: values["allow-python"] ?? false,
    blender: deps.blender,
  };
  const plan = planInstall(input);
  deps.log(explain(plan, input));
  const status = deps.run(plan);
  if (status === 0) deps.log(`Done. Restart Claude Code, then ask it to build something in Blender; /mcp shows the ${MCP_NAME} server.`);
  else deps.log(`claude mcp add failed with exit code ${status}. If ${MCP_NAME} is already added, remove it with: claude mcp remove --scope user ${MCP_NAME}`);
  return status;
}

export function installMain(): void {
  const here = dirname(fileURLToPath(import.meta.url));
  try {
    process.exitCode = install(process.argv.slice(2), {
      findClaude: () => findClaude(),
      run: runClaude,
      log: (line) => console.log(line),
      cwd: process.cwd(),
      serverPath: join(here, "index.js"),
      blender: process.env["BLENDER"],
    });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
