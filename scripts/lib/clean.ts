import { existsSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { activeSlots } from "./slots.js";
import { CACHE_MARKER, cacheRoot, repoRoot } from "./paths.js";

export type CleanResult = { removed: string[]; refusal?: string };

export function clean(root: string, everything: boolean, base: string = repoRoot): CleanResult {
  const removed: string[] = [];
  if (existsSync(root)) {
    if (!existsSync(join(root, CACHE_MARKER)) && readdirSync(root).length > 0) {
      return { removed, refusal: `${root} is not a Blendworks cache (it has no ${CACHE_MARKER} file), so it was left alone` };
    }
    const busy = activeSlots(root);
    if (busy.length > 0) return { removed, refusal: `Blender is running from ${root} (process ${busy.map((slot) => slot.pid).join(", ")}); try again when it stops` };
    rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    removed.push(root);
  }
  if (everything) {
    for (const name of ["dist"]) {
      const path = join(base, name);
      if (existsSync(path)) {
        rmSync(path, { recursive: true, force: true });
        removed.push(path);
      }
    }
  }
  return { removed };
}

export function cleanMain(argv: string[], env: NodeJS.ProcessEnv = process.env): number {
  const unknown = argv.filter((argument) => argument !== "--all");
  if (unknown.length > 0) {
    console.error(`unknown option ${unknown[0]}; usage: npm run clean [-- --all]  (--all also removes dist)`);
    return 2;
  }
  const result = clean(cacheRoot(env), argv.includes("--all"));
  if (result.refusal !== undefined) {
    console.error(result.refusal);
    return 1;
  }
  console.log(result.removed.length === 0 ? "nothing to clean" : `removed ${result.removed.join(", ")}`);
  return 0;
}
