export type BridgeArgs = Record<string, unknown>;

export interface BridgeRequest {
  id: number;
  cmd: string;
  args: BridgeArgs;
}

export interface BridgeFailure {
  code: string;
  message: string;
}

export type BridgeReply =
  | { id: number; ok: true; result: Record<string, unknown> }
  | { id: number; ok: false; error: BridgeFailure };

export class BridgeError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "BridgeError";
    this.code = code;
  }
}

export interface BridgeLink {
  call(cmd: string, args: BridgeArgs): Promise<Record<string, unknown>>;
  close(): Promise<void>;
  kill(): Promise<void>;
  onClose(listener: (reason: string) => void): void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseReply(line: string): BridgeReply {
  let message: unknown;
  try {
    message = JSON.parse(line);
  } catch {
    throw new BridgeError("protocol", `bridge sent a line that is not JSON: ${line.slice(0, 200)}`);
  }
  if (!isRecord(message) || typeof message["id"] !== "number" || typeof message["ok"] !== "boolean") {
    throw new BridgeError("protocol", `bridge sent a reply without id and ok: ${line.slice(0, 200)}`);
  }
  const id = message["id"];
  if (message["ok"]) {
    const result = message["result"];
    return { id, ok: true, result: isRecord(result) ? result : {} };
  }
  const error = message["error"];
  const code = isRecord(error) && typeof error["code"] === "string" ? error["code"] : "failed";
  const text = isRecord(error) && typeof error["message"] === "string" ? error["message"] : "the bridge reported a failure";
  return { id, ok: false, error: { code, message: text } };
}

const ID_IN_LINE = /"id"\s*:\s*(\d+)/;

export type Line =
  | { kind: "reply"; reply: BridgeReply }
  | { kind: "ignored" }
  | { kind: "garbled"; id: number | undefined; error: BridgeError };

export function readLine(line: string): Line {
  const trimmed = line.trim();
  if (trimmed === "") return { kind: "ignored" };
  try {
    return { kind: "reply", reply: parseReply(trimmed) };
  } catch (error) {
    if (!(error instanceof BridgeError)) throw error;
    if (/^\{\s*"id"\s*:\s*"quit"/.test(trimmed)) return { kind: "ignored" };
    const found = trimmed.startsWith("{") ? ID_IN_LINE.exec(trimmed) : null;
    return { kind: "garbled", id: found === null ? undefined : Number(found[1]), error };
  }
}
