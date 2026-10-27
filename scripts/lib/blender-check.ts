import { readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { blenderVersionOutput, resolveBlender, type ResolvedBlender } from "../../src/blender.js";
import { checkBlenderVersion } from "../../src/judge/version.js";
import { cacheRoot, ensureCacheRoot } from "./paths.js";

export type CheckedBlender = ResolvedBlender & { version: string };

type Memo = { path: string; size: number; mtimeMs: number; version: string };

function readMemo(file: string, path: string, size: number, mtimeMs: number): string | undefined {
  try {
    const memo = JSON.parse(readFileSync(file, "utf8")) as Memo;
    return memo.path === path && memo.size === size && memo.mtimeMs === mtimeMs ? memo.version : undefined;
  } catch {
    return undefined;
  }
}

export function checkedBlender(root: string = cacheRoot(), resolved: ResolvedBlender = resolveBlender()): CheckedBlender {
  const stats = statSync(resolved.path);
  const file = join(root, "blender-version.json");
  const remembered = readMemo(file, resolved.path, stats.size, stats.mtimeMs);
  if (remembered !== undefined) return { ...resolved, version: remembered };
  const version = checkBlenderVersion(blenderVersionOutput(resolved.path));
  ensureCacheRoot(root);
  const memo: Memo = { path: resolved.path, size: stats.size, mtimeMs: stats.mtimeMs, version };
  writeFileSync(file, JSON.stringify(memo));
  return { ...resolved, version };
}
