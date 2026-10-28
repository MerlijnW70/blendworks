export type ReferenceStyle = "uri" | "path" | "blend";

export type RefusalCode = "empty" | "encoding" | "control" | "scheme" | "absolute" | "escape" | "device" | "trailing" | "long";

export type PathVerdict = { ok: true; path: string } | { ok: false; code: RefusalCode; reason: string };

export const MAX_REFERENCE_LENGTH = 1024;
export const MAX_SEGMENT_LENGTH = 255;

export const REFUSAL_REASONS: Record<RefusalCode, string> = {
  empty: "the reference names no file",
  encoding: "the reference is not valid percent-encoding",
  control: "the reference holds a control character",
  scheme: "the reference has a scheme, a drive or a stream name",
  absolute: "the reference is an absolute or UNC path",
  escape: "the reference leaves the asset folder",
  device: "the reference names a Windows device",
  trailing: "a part of the reference ends in a dot or a space",
  long: `the reference is longer than ${MAX_REFERENCE_LENGTH} characters or has a part longer than ${MAX_SEGMENT_LENGTH}`,
};

const DEVICE_NAMES = /^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³]|conin\$|conout\$|clock\$)$/i;

function refused(code: RefusalCode): PathVerdict {
  return { ok: false, code, reason: REFUSAL_REASONS[code] };
}

function decoded(raw: string, style: ReferenceStyle): { text: string } | { refusal: RefusalCode } {
  if (style === "uri") {
    try {
      return { text: decodeURIComponent(raw) };
    } catch {
      return { refusal: "encoding" };
    }
  }
  if (style === "blend") return raw.startsWith("//") ? { text: raw.slice(2) } : { refusal: raw === "" ? "empty" : "absolute" };
  return { text: raw };
}

function segmentProblem(segment: string): RefusalCode | null {
  if (segment.length > MAX_SEGMENT_LENGTH) return "long";
  if (DEVICE_NAMES.test(segment.split(".")[0]!.replace(/ +$/, ""))) return "device";
  if (segment.endsWith(".") || segment.endsWith(" ")) return "trailing";
  return null;
}

export function checkReference(raw: string, style: ReferenceStyle): PathVerdict {
  const result = decoded(raw, style);
  if ("refusal" in result) return refused(result.refusal);
  const path = result.text;
  if (path.length === 0) return refused("empty");
  if (path.length > MAX_REFERENCE_LENGTH) return refused("long");
  if (/[\u0000-\u001f\u007f]/.test(path)) return refused("control");
  if (path.startsWith("/") || path.startsWith("\\")) return refused("absolute");
  if (path.includes(":")) return refused("scheme");
  const kept: string[] = [];
  for (const segment of path.split(/[/\\]/)) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") {
      if (kept.length === 0) return refused("escape");
      kept.pop();
      continue;
    }
    const problem = segmentProblem(segment);
    if (problem !== null) return refused(problem);
    kept.push(segment);
  }
  if (kept.length === 0) return refused("empty");
  return { ok: true, path: kept.join("/") };
}
