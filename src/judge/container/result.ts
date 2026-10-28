import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const EXIT = { pass: 0, fail: 1, usage: 2, error: 75 } as const;
export const RESULT_PREFIX = "BLENDWORKS-RESULT ";

export type Verdict = "pass" | "fail" | "error";

export type EntryResult = {
  blendworks: "judge-result";
  version: 1;
  kind: "asset" | "patch" | "probe";
  verdict: Verdict;
  exitCode: number;
  reason: string;
  commit: string | null;
  isolation: string | null;
  inputs: Record<string, string | null>;
  details: Record<string, unknown>;
};

export class EntryError extends Error {
  constructor(
    readonly verdict: Exclude<Verdict, "pass">,
    message: string,
  ) {
    super(message);
    this.name = "EntryError";
  }
}

export function exitCodeOf(verdict: Verdict): number {
  return verdict === "pass" ? EXIT.pass : verdict === "fail" ? EXIT.fail : EXIT.error;
}

export function result(kind: EntryResult["kind"], verdict: Verdict, reason: string, extra: Partial<Pick<EntryResult, "commit" | "isolation" | "inputs" | "details">> = {}): EntryResult {
  return {
    blendworks: "judge-result",
    version: 1,
    kind,
    verdict,
    exitCode: exitCodeOf(verdict),
    reason,
    commit: extra.commit ?? null,
    isolation: extra.isolation ?? null,
    inputs: extra.inputs ?? {},
    details: extra.details ?? {},
  };
}

export function emit(record: EntryResult, file: string | null): number {
  const line = JSON.stringify(record);
  if (file !== null) {
    try {
      mkdirSync(dirname(file), { recursive: true });
      writeFileSync(file, `${JSON.stringify(record, null, 2)}\n`);
    } catch {
      process.stderr.write(`could not write ${file}\n`);
    }
  }
  process.stdout.write(`${RESULT_PREFIX}${line}\n`);
  return record.exitCode;
}

export function parseResult(output: string): EntryResult | null {
  const line = output.split("\n").reverse().find((entry) => entry.startsWith(RESULT_PREFIX));
  if (line === undefined) return null;
  try {
    return JSON.parse(line.slice(RESULT_PREFIX.length)) as EntryResult;
  } catch {
    return null;
  }
}
