import { BridgeError, type BridgeLink } from "./protocol.js";

export const RECOVER_COMMAND = "recover";
export const RECOVER_TIMEOUT_MS = 300_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function describeRestored(result: Record<string, unknown>): string {
  const path = typeof result["path"] === "string" ? result["path"] : "the autosave";
  const when = typeof result["saved_at"] === "string" ? ` saved at ${result["saved_at"]}` : "";
  const why = typeof result["reason"] === "string" ? ` (${result["reason"]})` : "";
  const count = result["objects"];
  const objects = typeof count === "number" ? `; the scene has ${count} object${count === 1 ? "" : "s"}` : "";
  const skipped = Array.isArray(result["skipped"]) && result["skipped"].length > 0 ? ` The newer autosave could not be read: ${result["skipped"].join("; ")}.` : "";
  return `Reloaded ${path}${when}${why}${objects}. Changes after that autosave are lost; check with blender_scene_info before continuing.${skipped}`;
}

export function describeRecovery(result: Record<string, unknown>): string {
  if (result["restored"] === true) return describeRestored(result);
  const reason = typeof result["reason"] === "string" ? result["reason"] : "no autosave could be read";
  return `The scene is empty (${reason}), so rebuild it before continuing.`;
}

export async function recoverScene(link: BridgeLink, timeoutMs: number): Promise<string> {
  let timer: NodeJS.Timeout | undefined;
  const late = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new BridgeError("timeout", `reloading the autosave took longer than ${Math.round(timeoutMs / 1000)} s`)), timeoutMs);
  });
  try {
    const result = await Promise.race([link.call(RECOVER_COMMAND, {}), late]);
    return describeRecovery(isRecord(result) ? result : {});
  } finally {
    clearTimeout(timer);
  }
}
