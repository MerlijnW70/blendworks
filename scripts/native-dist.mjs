import { checkDist, DIST_DIR, releaseMode, sourceCommit, stageDist, writeManifest } from "./lib/native-dist.js";

const [command, ...rest] = process.argv.slice(2);
const flags = rest.filter((item) => item.startsWith("--"));
const folder = rest.find((item) => !item.startsWith("--")) ?? null;

function report(result) {
  for (const problem of result.problems) console.error(problem);
  console.log(`native cores: ${result.present.join(", ") || "none"}`);
  return result.ok ? 0 : 1;
}

try {
  const release = releaseMode(process.env, flags);
  if (command === "manifest" && folder) {
    writeManifest(folder, sourceCommit());
    process.exitCode = report(checkDist(folder, release));
  } else if (command === "stage") process.exitCode = report(stageDist(folder, DIST_DIR, release));
  else if (command === "verify") process.exitCode = report(checkDist(folder ?? DIST_DIR, release));
  else {
    console.error("usage: native-dist.mjs manifest <folder> | stage [<artifacts folder>] | verify [<folder>]  [--release]");
    process.exitCode = 2;
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
