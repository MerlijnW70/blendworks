import { lookup } from "node:dns/promises";
import { accessSync, constants, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { connect } from "node:net";
import { join } from "node:path";
import { containerShortfalls, containerText, probeContainer } from "../isolation.js";
import type { Layout } from "./inputs.js";
import { result, type EntryResult } from "./result.js";

export const HOST_PATHS = ["/mnt/c", "/mnt/f", "/mnt/wsl", "/mnt/host", "/host", "/run/desktop", "/var/run/docker.sock", "/run/docker.sock"];
const NETWORK_TIMEOUT_MS = 3000;

type Reach = { target: string; reached: boolean; error: string | null };

function connectTo(host: string, port: number): Promise<Reach> {
  return new Promise((resolve) => {
    const socket = connect({ host, port, timeout: NETWORK_TIMEOUT_MS });
    const done = (reached: boolean, error: string | null) => {
      socket.destroy();
      resolve({ target: `${host}:${port}`, reached, error });
    };
    socket.once("connect", () => done(true, null));
    socket.once("timeout", () => done(false, "timeout"));
    socket.once("error", (error: NodeJS.ErrnoException) => done(false, error.code ?? error.message));
  });
}

async function resolveName(name: string): Promise<Reach> {
  try {
    const timer = new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timeout")), NETWORK_TIMEOUT_MS).unref());
    await Promise.race([lookup(name), timer]);
    return { target: name, reached: true, error: null };
  } catch (error) {
    return { target: name, reached: false, error: (error as NodeJS.ErrnoException).code ?? (error as Error).message };
  }
}

function readable(path: string): string {
  if (!existsSync(path)) return "absent";
  try {
    accessSync(path, constants.R_OK);
    return readdirEntries(path);
  } catch {
    return "unreadable";
  }
}

function readdirEntries(path: string): string {
  try {
    return `present (${readdirSync(path).length} entries)`;
  } catch {
    return "present";
  }
}

function writable(folder: string): string {
  const path = join(folder, `.blendworks-probe-${process.pid}`);
  try {
    writeFileSync(path, "probe");
    rmSync(path, { force: true });
    return "writable";
  } catch (error) {
    return `refused (${(error as NodeJS.ErrnoException).code ?? "error"})`;
  }
}

function mounts(): { point: string; options: string; type: string }[] {
  try {
    return readFileSync("/proc/self/mountinfo", "utf8")
      .split("\n")
      .filter((line) => line.trim() !== "")
      .map((line) => {
        const fields = line.split(" ");
        const dash = fields.indexOf("-");
        return { point: (fields[4] ?? "").replace(/\\040/g, " "), options: (fields[5] ?? "").split(",")[0] ?? "", type: fields[dash + 1] ?? "" };
      });
  } catch {
    return [];
  }
}

function capabilities(): string | null {
  try {
    return /^CapEff:\s*(\S+)/m.exec(readFileSync("/proc/self/status", "utf8"))?.[1] ?? null;
  } catch {
    return null;
  }
}

export async function probe(layout: Layout, extra: string[], commit: string | null = null): Promise<EntryResult> {
  try {
    mkdirSync(layout.scratch, { recursive: true });
  } catch {
    process.stderr.write(`could not make ${layout.scratch}\n`);
  }
  const container = probeContainer();
  const network = [await resolveName("registry.npmjs.org"), await connectTo("1.1.1.1", 443), await connectTo("8.8.8.8", 53), await connectTo("host.docker.internal", 2375)];
  const host = Object.fromEntries([...HOST_PATHS, ...extra].map((path) => [path, readable(path)]));
  const writes = Object.fromEntries(["/", "/etc", "/opt/blendworks", layout.work, layout.spec, "/tmp", layout.scratch].map((folder) => [folder, existsSync(folder) ? writable(folder) : "absent"]));
  const problems = [
    ...(container === null ? ["not in a container"] : containerShortfalls(container)),
    ...network.filter((entry) => entry.reached).map((entry) => `reached ${entry.target}`),
    ...Object.entries(host).filter(([, state]) => state !== "absent").map(([path, state]) => `${path} is ${state}`),
    ...["/", "/etc", "/opt/blendworks", layout.work, layout.spec].filter((folder) => writes[folder] === "writable").map((folder) => `${folder} is writable`),
    ...(writes[layout.scratch] === "writable" ? [] : [`the work folder ${layout.scratch} is not writable`]),
    ...(capabilities() === "0000000000000000" ? [] : [`effective capabilities ${capabilities() ?? "unknown"}`]),
  ];
  const details = { network, host, writes, mounts: mounts(), capabilities: capabilities(), uid: process.getuid?.() ?? null, gid: process.getgid?.() ?? null, problems };
  const isolation = container === null ? null : containerText(container);
  return result("probe", problems.length === 0 ? "pass" : "fail", problems.length === 0 ? "no network, no host folder, writes only to the work folders" : problems.join("; "), { commit, isolation, details });
}
