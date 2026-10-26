import { existsSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";

const WINDOWS_DEFAULT = "F:/tools/blender-5.2.3-windows-x64/blender.exe";
const LINUX_DEFAULT = join(homedir(), "tools", "blender", "blender");

export function blenderPath(): string {
  const fromEnv = process.env["BLENDER"];
  if (fromEnv) return fromEnv;
  const fallback = platform() === "win32" ? WINDOWS_DEFAULT : LINUX_DEFAULT;
  if (!existsSync(fallback)) throw new Error(`Blender not found; set BLENDER to the blender binary (looked at ${fallback})`);
  return fallback;
}

export const BLENDER_VERSION = "5.2";
