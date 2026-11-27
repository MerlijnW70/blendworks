export type Content = { type: "text"; text: string } | { type: "image"; data: string; mimeType: string };

export const MAX_TEXT_CHARS = 64_000;

const PAGING_HINTS: Record<string, string> = {
  scene_info: "Ask for a page: scene_info takes detail (summary, objects or full), names (a glob such as \"Bolt*\"), limit and offset.",
  run_python: "Print less, or set result to a smaller value.",
  uv_info: "Ask for fewer objects with names.",
  validate: "Validate fewer calls at a time, and fix the problems already listed first.",
  image_info: "Ask for fewer images with names.",
};

export function capText(cmd: string, text: string, limit = MAX_TEXT_CHARS): string {
  if (text.length <= limit) return text;
  const hint = PAGING_HINTS[cmd] ?? "Ask for less, for example fewer names.";
  return `${text.slice(0, limit)}\n[cut: this result has ${text.length} characters and results stop at ${limit}. ${hint}]`;
}

interface FoundImage {
  label: string;
  data: string;
  mimeType: string;
  width: unknown;
  height: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asImage(value: Record<string, unknown>, index: number): FoundImage | undefined {
  const mimeType = value["mimeType"];
  const data = value["data"];
  if (typeof mimeType !== "string" || !mimeType.startsWith("image/") || typeof data !== "string") return undefined;
  const label = [value["view"], value["camera"], value["name"]].find((entry): entry is string => typeof entry === "string" && entry !== "");
  return { label: label ?? `image ${index}`, data, mimeType, width: value["width"], height: value["height"] };
}

function extractImages(value: unknown, found: FoundImage[]): unknown {
  if (Array.isArray(value)) return value.map((entry) => extractImages(entry, found));
  if (!isRecord(value)) return value;
  const image = asImage(value, found.length + 1);
  if (image !== undefined) {
    found.push(image);
    const { data: _data, ...rest } = value;
    return { ...rest, data: `<${image.mimeType} shown as image ${found.length}>` };
  }
  const out: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) out[key] = extractImages(entry, found);
  return out;
}

const SUMMARISED = new Set(["images", "engine", "samples", "seed", "geometry_objects", "device", "device_label", "shading"]);

function previewSummary(found: FoundImage[], result: Record<string, unknown>): string {
  const first = found[0];
  const size = first !== undefined && typeof first.width === "number" && typeof first.height === "number" ? ` at ${first.width}x${first.height} px` : "";
  const engine = typeof result["engine"] === "string" ? result["engine"] : undefined;
  const samples = typeof result["samples"] === "number" ? result["samples"] : undefined;
  const on = typeof result["device_label"] === "string" ? ` on ${result["device_label"]}` : "";
  const how = engine !== undefined && samples !== undefined ? ` with ${engine}${on}, ${samples} samples` : "";
  const shading = typeof result["shading"] === "string" && result["shading"] !== "shaded" ? `, ${result["shading"]} shading` : "";
  const plural = found.length === 1 ? "" : "s";
  const extra = Object.fromEntries(Object.entries(result).filter(([key]) => !SUMMARISED.has(key)));
  const details = Object.keys(extra).length > 0 ? ` ${JSON.stringify(extra)}` : "";
  return `Rendered ${found.length} view${plural}${size}${how}${shading}: ${found.map((image) => image.label).join(", ")}.${details}`;
}

export function toContent(cmd: string, result: Record<string, unknown>, notices: string[] = []): Content[] {
  const found: FoundImage[] = [];
  const rest = extractImages(result, found);
  const content: Content[] = notices.map((notice) => ({ type: "text", text: notice }));
  if (found.length === 0) {
    content.push({ type: "text", text: capText(cmd, JSON.stringify(rest)) });
    return content;
  }
  const summary = cmd === "render_preview" ? previewSummary(found, result) : JSON.stringify(rest);
  content.push({ type: "text", text: capText(cmd, summary) });
  for (const image of found) content.push({ type: "image", data: image.data, mimeType: image.mimeType });
  return content;
}
