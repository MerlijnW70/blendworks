import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";

const blender =
  process.env.BLENDER ??
  (platform() === "win32" ? "F:/tools/blender-5.2.3-windows-x64/blender.exe" : join(homedir(), "tools", "blender", "blender"));
const dir = join(process.cwd(), "bridge", "tests");
const files = existsSync(dir) ? readdirSync(dir).filter((name) => /^test_.*\.py$/.test(name)).sort() : [];
let failed = 0;
for (const file of files) {
  try {
    execFileSync(blender, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(dir, file)], { stdio: "pipe" });
    console.log(`ok   ${file}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${file}`);
    console.log(String(error.stdout ?? "").slice(-4000));
    console.log(String(error.stderr ?? "").slice(-2000));
  }
}
console.log(`${files.length - failed} of ${files.length} bridge test files passed`);
process.exit(failed === 0 ? 0 : 1);
