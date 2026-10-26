import { execFileSync } from "node:child_process";
import { homedir, platform } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const bridge = dirname(fileURLToPath(import.meta.url));
const output = resolve(process.argv[2] ?? join(bridge, "..", "dist", "blendworks-addon.zip"));
const blender =
  process.env.BLENDER ??
  (platform() === "win32" ? "F:/tools/blender-5.2.3-windows-x64/blender.exe" : join(homedir(), "tools", "blender", "blender"));

execFileSync(blender, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(bridge, "build_addon.py"), "--", output], {
  stdio: ["ignore", "ignore", "inherit"],
});
console.log(`add-on: ${output}`);
