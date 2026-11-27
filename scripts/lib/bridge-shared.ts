import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { StringDecoder } from "node:string_decoder";
import { thisMachine } from "../../src/blender.js";
import { LineSplitter } from "./progress.js";

export const SHARE_VARIABLE = "BLENDWORKS_SHARED_BLENDER";
export const SHARED_MARK = "BLENDWORKS-SHARED ";
export const FRESH_MARK = /^BLENDWORKS_FRESH_PROCESS\s*=\s*["'](.+)["']\s*$/m;
export const BATCH_SECONDS = 60;
export const BATCH_FILES = 12;

const OWN_PEAK_MEMORY = "asserts the peak resident memory of its own Blender process against a budget, and files before it in a shared process would count";

export const FRESH_FILES: Record<string, string> = {
  "test_render_views_copies.py": OWN_PEAK_MEMORY,
  "test_render_views_large.py": OWN_PEAK_MEMORY,
  "test_constraints.py": "its rig has a dependency cycle (the IK solver of the root and the parent of the pole bone), whose evaluation order Blender does not fix; in a shared process it once failed its baked-pose test, which no order of the other files in one process and no fresh run reproduced",
};

export type Sharing = { shared: boolean; reason: string };

export function containerMarker(exists: (path: string) => boolean = existsSync): string | null {
  return ["/.dockerenv", "/run/.containerenv"].find((path) => exists(path)) ?? null;
}

export function bridgeSharing(env: NodeJS.ProcessEnv = process.env, marker: string | null = containerMarker(), quotaLimited: boolean = thisMachine().source === "cgroup quota"): Sharing {
  const forced = env[SHARE_VARIABLE];
  if (forced === "0") return { shared: false, reason: `${SHARE_VARIABLE}=0` };
  if (forced === "1") return { shared: true, reason: `${SHARE_VARIABLE}=1` };
  if (marker !== null || quotaLimited) return { shared: false, reason: `a container or CPU-limited sandbox keeps a fresh Blender per file (${marker ?? "cgroup CPU quota"})` };
  return { shared: true, reason: "bridge test files share Blender processes, with a factory reset between files" };
}

export function freshReason(file: string, directory: string, listed: Record<string, string> = FRESH_FILES): string | undefined {
  if (Object.hasOwn(listed, file)) return listed[file];
  try {
    return FRESH_MARK.exec(readFileSync(join(directory, file), "utf8"))?.[1]?.trim() || undefined;
  } catch {
    return undefined;
  }
}

export type Work = { kind: "fresh"; file: string } | { kind: "shared"; files: string[] };

export function takeWork(queue: string[], shareable: (file: string) => boolean, expected: Record<string, number>, seconds: number = BATCH_SECONDS, most: number = BATCH_FILES): Work | undefined {
  const first = queue.shift();
  if (first === undefined) return undefined;
  if (!shareable(first)) return { kind: "fresh", file: first };
  const files = [first];
  let total = expected[first] ?? 1;
  while (files.length < most && total < seconds) {
    const index = queue.findIndex((file) => shareable(file));
    if (index < 0) break;
    const [next] = queue.splice(index, 1) as [string];
    files.push(next);
    total += expected[next] ?? 1;
  }
  return { kind: "shared", files };
}

export type SharedEvent = { event: "start"; file: string } | { event: "end"; file: string; passed: boolean; seconds: number; leaks: string[] };

export function parseSharedEvent(line: string): SharedEvent | undefined {
  if (!line.startsWith(SHARED_MARK)) return undefined;
  try {
    const parsed = JSON.parse(line.slice(SHARED_MARK.length)) as Partial<SharedEvent> & { event?: unknown };
    if (parsed.event === "start" && typeof parsed.file === "string") return { event: "start", file: parsed.file };
    if (parsed.event === "end" && typeof parsed.file === "string") return { event: "end", file: parsed.file, passed: parsed.passed === true, seconds: Number(parsed.seconds ?? 0), leaks: Array.isArray(parsed.leaks) ? parsed.leaks.map(String) : [] };
  } catch {
    return undefined;
  }
  return undefined;
}

export class SharedStream {
  private readonly decoder = new StringDecoder("utf8");
  private readonly lines = new LineSplitter();
  private current: { file: string; output: string[] } | undefined;

  constructor(
    private readonly onStart: (file: string) => void,
    private readonly onEnd: (event: Extract<SharedEvent, { event: "end" }>, output: string) => void,
  ) {}

  push(chunk: Buffer): void {
    for (const line of this.lines.push(this.decoder.write(chunk))) this.line(line);
  }

  private line(line: string): void {
    const event = parseSharedEvent(line);
    if (event === undefined) {
      this.current?.output.push(line);
      return;
    }
    if (event.event === "start") {
      this.current = { file: event.file, output: [] };
      this.onStart(event.file);
      return;
    }
    const output = this.current?.file === event.file ? this.current.output.join("\n") : "";
    this.current = undefined;
    this.onEnd(event, output);
  }

  unfinished(): { file: string; output: string } | undefined {
    const rest = this.lines.rest();
    if (rest !== "") this.line(rest);
    return this.current === undefined ? undefined : { file: this.current.file, output: this.current.output.join("\n") };
  }
}

export type TestOutcome = { name: string; passed: boolean };

export function harnessOutcomes(output: string): TestOutcome[] {
  const out: TestOutcome[] = [];
  for (const line of output.split(/\r?\n/)) {
    const match = /^(ok  |FAIL) (test_\w+)$/.exec(line.trimEnd());
    if (match !== null) out.push({ name: match[2] as string, passed: match[1] === "ok  " });
  }
  return out;
}
