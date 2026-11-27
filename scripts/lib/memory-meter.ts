import { type ChildProcess, spawn } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { LineSplitter } from "./progress.js";
import { type Holder, slotHolders } from "./slots.js";
import { topLevelRun } from "./durations.js";
import type { Peaks } from "./memory.js";

export type ProcessInfo = { pid: number; ppid: number; peakMb: number; nowMb: number };

export type ProcessTable = Map<number, ProcessInfo>;

export type ProcessSource = { table(): ProcessTable | undefined; close(): void };

function linuxProcess(pid: number): ProcessInfo | undefined {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
    const ppid = Number(stat.slice(stat.lastIndexOf(")") + 2).split(" ")[1]);
    const status = readFileSync(`/proc/${pid}/status`, "utf8");
    const peak = /^VmHWM:\s+(\d+)\s+kB/m.exec(status);
    const now = /^VmRSS:\s+(\d+)\s+kB/m.exec(status);
    return { pid, ppid, peakMb: peak === null ? 0 : Number(peak[1]) / 1024, nowMb: now === null ? 0 : Number(now[1]) / 1024 };
  } catch {
    return undefined;
  }
}

export function linuxSource(): ProcessSource {
  return {
    table() {
      const table: ProcessTable = new Map();
      for (const name of readdirSync("/proc")) {
        if (!/^\d+$/.test(name)) continue;
        const info = linuxProcess(Number(name));
        if (info !== undefined) table.set(info.pid, info);
      }
      return table;
    },
    close() {},
  };
}

const WINDOWS_SAMPLER = `
$ErrorActionPreference = 'SilentlyContinue'
while ($true) {
  $rows = Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,PeakWorkingSetSize,WorkingSetSize | ForEach-Object { "$($_.ProcessId),$($_.ParentProcessId),$($_.PeakWorkingSetSize),$($_.WorkingSetSize)" }
  [Console]::Out.WriteLine(($rows -join ';'))
  [Console]::Out.Flush()
  Start-Sleep -Milliseconds INTERVAL
}`;

export function parseWindowsRows(line: string): ProcessTable {
  const table: ProcessTable = new Map();
  for (const row of line.split(";")) {
    const [pid, ppid, peakKb, nowBytes] = row.split(",").map(Number);
    if (pid === undefined || ppid === undefined || peakKb === undefined || !Number.isFinite(pid) || !Number.isFinite(ppid)) continue;
    table.set(pid, { pid, ppid, peakMb: Number.isFinite(peakKb) ? peakKb / 1024 : 0, nowMb: nowBytes !== undefined && Number.isFinite(nowBytes) ? nowBytes / (1024 * 1024) : 0 });
  }
  return table;
}

export function windowsSource(intervalMs: number): ProcessSource {
  let latest: ProcessTable | undefined;
  const child: ChildProcess = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", WINDOWS_SAMPLER.replace("INTERVAL", String(intervalMs))], { stdio: ["ignore", "pipe", "ignore"], windowsHide: true });
  const lines = new LineSplitter();
  child.stdout?.on("data", (chunk: Buffer) => {
    for (const line of lines.push(chunk.toString("utf8"))) if (line.trim() !== "") latest = parseWindowsRows(line.trim());
  });
  child.on("error", () => undefined);
  child.unref();
  const stop = (): void => {
    if (child.exitCode === null) child.kill();
  };
  process.once("exit", stop);
  return {
    table: () => latest,
    close() {
      process.removeListener("exit", stop);
      stop();
    },
  };
}

export function defaultSource(intervalMs: number): ProcessSource | undefined {
  if (process.platform === "linux") return linuxSource();
  if (process.platform === "win32") return windowsSource(intervalMs);
  return undefined;
}

function descendants(table: ProcessTable, root: number, includeRoot: boolean): number[] {
  const children = new Map<number, number[]>();
  for (const info of table.values()) {
    if (info.pid === info.ppid) continue;
    const list = children.get(info.ppid) ?? [];
    list.push(info.pid);
    children.set(info.ppid, list);
  }
  const out: number[] = includeRoot && table.has(root) ? [root] : [];
  const stack = [...(children.get(root) ?? [])];
  const seen = new Set<number>(out);
  while (stack.length > 0) {
    const pid = stack.pop() as number;
    if (seen.has(pid)) continue;
    seen.add(pid);
    out.push(pid);
    stack.push(...(children.get(pid) ?? []));
  }
  return out;
}

export function filePeaks(holders: Holder[], table: ProcessTable): Peaks {
  const members = new Map<string, Map<number, boolean>>();
  for (const holder of holders) {
    const file = holder.child?.file ?? holder.file;
    if (file === undefined || !topLevelRun(file, holder.stage)) continue;
    const pids = holder.child === undefined ? descendants(table, holder.pid, false) : descendants(table, holder.child.pid, true);
    const set = members.get(file) ?? new Map<number, boolean>();
    for (const pid of pids) set.set(pid, holder.child?.shared === true);
    members.set(file, set);
  }
  const out: Peaks = {};
  for (const [file, pids] of members) out[file] = [...pids].reduce((sum, [pid, shared]) => sum + ((shared ? table.get(pid)?.nowMb : table.get(pid)?.peakMb) ?? 0), 0);
  return out;
}

export class MemoryMeter {
  private readonly peaks = new Map<string, number>();
  private readonly timer: NodeJS.Timeout;
  private samples = 0;

  constructor(
    private readonly directory: string,
    private readonly source: ProcessSource,
    intervalMs: number,
  ) {
    this.timer = setInterval(() => this.sample(), intervalMs);
    this.timer.unref();
  }

  sample(): void {
    const table = this.source.table();
    if (table === undefined) return;
    this.samples += 1;
    for (const [file, mb] of Object.entries(filePeaks(slotHolders(this.directory), table))) {
      if (mb > (this.peaks.get(file) ?? 0)) this.peaks.set(file, mb);
    }
  }

  sampleCount(): number {
    return this.samples;
  }

  stop(): Peaks {
    clearInterval(this.timer);
    this.sample();
    this.source.close();
    return Object.fromEntries([...this.peaks].map(([file, mb]) => [file, Math.round(mb)]));
  }
}

export function startMemoryMeter(directory: string, intervalMs: number = process.platform === "win32" ? 1000 : 250): MemoryMeter | undefined {
  const source = defaultSource(intervalMs);
  return source === undefined ? undefined : new MemoryMeter(directory, source, intervalMs);
}
