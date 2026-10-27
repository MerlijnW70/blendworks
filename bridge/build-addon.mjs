import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkedBlender } from "../scripts/lib/blender-check.js";
import { runBlender } from "../scripts/lib/run.js";

const bridge = dirname(fileURLToPath(import.meta.url));
const output = resolve(process.argv[2] ?? join(bridge, "..", "dist", "blendworks-addon.zip"));
const blender = checkedBlender();

const result = await runBlender(blender.path, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(bridge, "build_addon.py"), "--", output]);
if (result.code !== 0) {
  process.stderr.write(result.stderr);
  process.exit(result.code ?? 1);
}
console.log(`add-on: ${output}`);
