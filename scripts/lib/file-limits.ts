export const FILE_LIMIT_VARIABLE = "BLENDWORKS_FILE_LIMIT_S";
export const HEARTBEAT_VARIABLE = "BLENDWORKS_HEARTBEAT_S";

export const DEFAULT_FILE_LIMIT_S = 600;
export const DEFAULT_HEARTBEAT_S = 60;

export const EXEMPT_FILES: Record<string, string> = {
  "test/judge/equivalence.test.ts": "it judges every stored fixture, so its work grows with the fixture count; each judge run has its own work budget (CASE_WORK_MS), which stops a hung run within five minutes",
};

function seconds(name: string, fallback: number, env: NodeJS.ProcessEnv): number {
  const value = Number(env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

export function fileLimitMs(env: NodeJS.ProcessEnv = process.env): number {
  return seconds(FILE_LIMIT_VARIABLE, DEFAULT_FILE_LIMIT_S, env) * 1000;
}

export function heartbeatMs(env: NodeJS.ProcessEnv = process.env): number {
  return seconds(HEARTBEAT_VARIABLE, DEFAULT_HEARTBEAT_S, env) * 1000;
}

export function isExempt(file: string, exempt: Record<string, string> = EXEMPT_FILES): boolean {
  return Object.hasOwn(exempt, file);
}
