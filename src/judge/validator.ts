import { readFileSync, realpathSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { basename, dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { Worker } from "node:worker_threads";
import { z } from "zod";

export const VALIDATOR_PACKAGE = "gltf-validator";
export const VALIDATOR_DEFAULTS = { maxBytes: 128 * 1024 * 1024, heapMb: 2048, timeoutMs: 300_000 };
export const SEVERITIES = ["error", "warning", "info", "hint"] as const;

export type ValidationIssue = { code: string; severity: (typeof SEVERITIES)[number]; pointer: string | null; message: string };

export type Validation = {
  validator: string;
  seconds: number;
  bytes: number;
  errors: number;
  warnings: number;
  infos: number;
  hints: number;
  issues: ValidationIssue[];
  refused: string[];
};

export type ValidationLimits = { maxBytes: number; heapMb: number; timeoutMs: number };

export class ValidationError extends Error {
  constructor(
    readonly code: "too_large" | "failed" | "timeout" | "crashed",
    message: string,
  ) {
    super(message);
    this.name = "ValidationError";
  }
}

const WORKER = `
const { parentPort, workerData } = require("node:worker_threads");
const validator = require(workerData.modulePath);
const pending = new Map();
let next = 0;
parentPort.on("message", (reply) => {
  const waiting = pending.get(reply.id);
  if (waiting === undefined) return;
  pending.delete(reply.id);
  if (reply.data) waiting.resolve(reply.data);
  else waiting.reject(reply.error);
});
const externalResourceFunction = (uri) =>
  new Promise((resolve, reject) => {
    const id = next++;
    pending.set(id, { resolve, reject });
    parentPort.postMessage({ kind: "resource", id, uri });
  });
validator
  .validateBytes(new Uint8Array(workerData.bytes), { uri: workerData.name, format: workerData.format, writeTimestamp: false, maxIssues: 0, externalResourceFunction })
  .then(
    (report) => parentPort.postMessage({ kind: "done", report, version: validator.version() }),
    (error) => parentPort.postMessage({ kind: "failed", message: String(error) }),
  );
`;

const text = (limit: number) => z.string().transform((value) => value.slice(0, limit));

const reportSchema = z.object({
  issues: z.object({
    numErrors: z.number().int().nonnegative(),
    numWarnings: z.number().int().nonnegative(),
    numInfos: z.number().int().nonnegative(),
    numHints: z.number().int().nonnegative(),
    messages: z.array(z.object({ code: text(100), message: text(2000), severity: z.number().int().min(0).max(3), pointer: text(2000).optional() })),
    truncated: z.boolean(),
  }),
});

const messageSchema = z.union([
  z.object({ kind: z.literal("resource"), id: z.number().int(), uri: z.string() }),
  z.object({ kind: z.literal("done"), report: z.unknown(), version: z.string().max(100) }),
  z.object({ kind: z.literal("failed"), message: z.string() }),
]);

export function resolveResource(assetPath: string, uri: string): { path: string } | { refused: string } {
  let decoded: string;
  try {
    decoded = decodeURIComponent(uri);
  } catch {
    return { refused: "the URI is not valid percent-encoding" };
  }
  if (decoded.includes(":") || decoded.startsWith("/") || decoded.startsWith("\\") || isAbsolute(decoded)) {
    return { refused: "the URI has a scheme or an absolute path" };
  }
  const folder = realpathSync(dirname(assetPath));
  const target = resolve(folder, decoded);
  let real: string;
  try {
    real = realpathSync(target);
  } catch {
    return { refused: "the file does not exist" };
  }
  const inside = relative(folder, real);
  if (inside === "" || inside.startsWith(`..${sep}`) || inside === ".." || isAbsolute(inside)) {
    return { refused: "the file is outside the asset folder" };
  }
  if (!statSync(real).isFile()) return { refused: "the URI is not a file" };
  return { path: real };
}

function issueList(report: z.infer<typeof reportSchema>): ValidationIssue[] {
  return report.issues.messages.map((message) => ({
    code: message.code,
    severity: SEVERITIES[message.severity] ?? "hint",
    pointer: message.pointer ?? null,
    message: message.message,
  }));
}

export function validatorModulePath(): string {
  return createRequire(import.meta.url).resolve(VALIDATOR_PACKAGE);
}

function readCapped(path: string, room: number): ArrayBuffer | null {
  if (statSync(path).size > room) return null;
  const data = readFileSync(path);
  if (data.byteLength > room) return null;
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

export async function validateGltf(assetPath: string, format: "glb" | "gltf", limits: ValidationLimits): Promise<Validation> {
  const started = performance.now();
  const bytes = readCapped(assetPath, limits.maxBytes);
  if (bytes === null) {
    throw new ValidationError("too_large", `the asset is ${statSync(assetPath).size} bytes, over the validator's cap of ${limits.maxBytes}`);
  }
  let total = bytes.byteLength;
  const refused: string[] = [];
  const worker = new Worker(WORKER, {
    eval: true,
    workerData: { modulePath: validatorModulePath(), bytes, name: basename(assetPath), format },
    transferList: [bytes],
    resourceLimits: { maxOldGenerationSizeMb: limits.heapMb },
    stdout: true,
    stderr: true,
  });
  worker.stdout.resume();
  worker.stderr.resume();
  const serve = (id: number, uri: string) => {
    const found = resolveResource(assetPath, uri);
    let reason = "refused" in found ? found.refused : null;
    if ("path" in found) {
      const data = readCapped(found.path, limits.maxBytes - total);
      if (data === null) reason = `the file would take the validator over its cap of ${limits.maxBytes} bytes`;
      else {
        total += data.byteLength;
        worker.postMessage({ id, data: new Uint8Array(data) }, [data]);
        return;
      }
    }
    refused.push(`${uri.slice(0, 200)}: ${reason}`);
    worker.postMessage({ id, error: `refused by the judge: ${reason}` });
  };
  try {
    const finished = await new Promise<{ report: unknown; version: string }>((resolveRun, rejectRun) => {
      const timer = setTimeout(() => rejectRun(new ValidationError("timeout", `the validator took longer than ${limits.timeoutMs / 1000} s and was stopped`)), limits.timeoutMs);
      const settle = (action: () => void) => {
        clearTimeout(timer);
        action();
      };
      worker.on("message", (raw: unknown) => {
        const message = messageSchema.safeParse(raw);
        if (!message.success) return settle(() => rejectRun(new ValidationError("failed", "the validator sent a malformed message")));
        const value = message.data;
        if (value.kind === "resource") return serve(value.id, value.uri);
        if (value.kind === "failed") return settle(() => rejectRun(new ValidationError("failed", `the validator refused the file: ${value.message.slice(0, 400)}`)));
        settle(() => resolveRun({ report: value.report, version: value.version }));
      });
      worker.on("error", (error: Error) => settle(() => rejectRun(new ValidationError("crashed", `the validator stopped: ${error.message.slice(0, 400)}`))));
      worker.on("exit", (code) => settle(() => rejectRun(new ValidationError("crashed", `the validator exited with code ${code} before it finished`))));
    });
    const report = reportSchema.safeParse(finished.report);
    if (!report.success) throw new ValidationError("failed", "the validator wrote a malformed report");
    const { issues } = report.data;
    if (issues.truncated) throw new ValidationError("failed", "the validator truncated its issue list");
    return {
      validator: finished.version,
      seconds: Math.round(performance.now() - started) / 1000,
      bytes: total,
      errors: issues.numErrors,
      warnings: issues.numWarnings,
      infos: issues.numInfos,
      hints: issues.numHints,
      issues: issueList(report.data),
      refused: refused.sort(),
    };
  } finally {
    await worker.terminate();
  }
}
