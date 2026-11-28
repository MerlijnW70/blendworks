import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkDist, DIST_DIR, releaseMode } from "../scripts/lib/native-dist.js";
import { checkedBlender } from "../scripts/lib/blender-check.js";
import { runBlender } from "../scripts/lib/run.js";

const bridge = dirname(fileURLToPath(import.meta.url));
const output = resolve(process.argv.slice(2).find((item) => !item.startsWith("--")) ?? join(bridge, "..", "dist", "blendworks-addon.zip"));
const cores = checkDist(DIST_DIR, releaseMode(process.env, process.argv));
if (!cores.ok) {
  for (const problem of cores.problems) console.error(problem);
  process.exit(1);
}
const blender = checkedBlender();

const result = await runBlender(blender.path, ["--background", "--factory-startup", "--python-exit-code", "1", "--python", join(bridge, "build_addon.py"), "--", output]);
if (result.code !== 0) {
  process.stderr.write(result.stderr);
  process.exit(result.code ?? 1);
}
console.log(`add-on: ${output}`);
