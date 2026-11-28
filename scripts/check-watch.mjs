import { lowerOwnPriority, parseWatchArgs, watch } from "./lib/watch.js";

const options = parseWatchArgs(process.argv.slice(2));
if (typeof options === "string") {
  console.error(options);
  process.exitCode = 2;
} else {
  lowerOwnPriority();
  console.log(`watching ${options.branch} of ${options.repo} at low priority with ${process.env.BLENDWORKS_JOBS ?? "the host's"} Blender slots; results in ${options.out}`);
  const results = await watch(options);
  if (options.once) process.exitCode = results.every((result) => result.passed) ? 0 : 1;
}
