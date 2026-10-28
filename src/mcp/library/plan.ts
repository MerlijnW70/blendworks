import { type AssetType, byResolution, checkRelativePath, fileNameOf, LibraryError, megabytes } from "./common.js";
import { type RemoteFile, remoteFileSchema, type Resolutions, type SetFiles } from "./schemas.js";
import { NOT_MAPS, resolutionsOf } from "./search.js";

export const FORMATS: Record<AssetType, readonly string[]> = { hdri: ["hdr", "exr"], texture: ["jpg", "png", "exr"], model: ["gltf"] };
export const DEFAULT_FORMAT: Record<AssetType, string> = { hdri: "hdr", texture: "jpg", model: "gltf" };
export const DEFAULT_MAPS = ["Diffuse", "nor_gl", "Rough", "Metal", "AO", "Displacement", "Mask"] as const;

export interface PlannedFile {
  path: string;
  url: string;
  size: number;
  md5: string;
}

export interface Plan {
  type: AssetType;
  resolution: string;
  format: string;
  files: PlannedFile[];
  total: number;
  main?: string;
  maps?: Record<string, string>;
}

export interface PlanRequest {
  resolution: string;
  format?: string | undefined;
  maps?: string[] | undefined;
}

type AnyFiles = SetFiles | { hdri: Resolutions };

function planned(path: string, file: { url: string; size: number; md5: string }): PlannedFile {
  return { path: checkRelativePath(path), url: file.url, size: file.size, md5: file.md5 };
}

function problemWith(listed: unknown): string | undefined {
  const parsed = remoteFileSchema.safeParse(listed);
  if (parsed.success) return undefined;
  const issue = parsed.error.issues[0];
  const where = issue === undefined || issue.path.length === 0 ? "the entry" : issue.path.map(String).join(".");
  return `${where} ${issue?.message ?? "is invalid"}`;
}

function usableResolutions(resolutions: Resolutions | undefined, format: string): string[] {
  return Object.entries(resolutions ?? {})
    .filter(([, formats]) => problemWith(formats[format]) === undefined)
    .map(([resolution]) => resolution)
    .sort(byResolution);
}

function pick(resolutions: Resolutions | undefined, resolution: string, format: string, what: string): RemoteFile {
  const formats = resolutions?.[resolution];
  if (formats === undefined) {
    const offered = Object.keys(resolutions ?? {}).sort(byResolution);
    throw new LibraryError("refused", `${what} has no ${resolution} resolution; it offers ${offered.join(", ") || "none"}`);
  }
  const listed = formats[format];
  if (listed === undefined) throw new LibraryError("refused", `${what} has no ${format} file at ${resolution}; it offers ${Object.keys(formats).join(", ")}`);
  const problem = problemWith(listed);
  if (problem !== undefined) {
    const url = typeof (listed as { url?: unknown }).url === "string" ? ` (${String((listed as { url: string }).url).split("/").pop()})` : "";
    const others = usableResolutions(resolutions, format).filter((other) => other !== resolution);
    const advice = others.length > 0 ? `use another resolution, ${others.join(", ")}` : "no other resolution of this format is listed correctly";
    throw new LibraryError("refused", `${what} at ${resolution}${url} is listed badly by Poly Haven (${problem}), so it is not downloaded; ${advice}`);
  }
  return listed as RemoteFile;
}

function availableMaps(files: SetFiles): string[] {
  return Object.keys(files).filter((name) => !NOT_MAPS.has(name));
}

function textureFiles(files: SetFiles, request: PlanRequest, format: string): { files: PlannedFile[]; maps: Record<string, string> } {
  const available = availableMaps(files);
  let wanted: string[];
  if (request.maps !== undefined) {
    const unknown = request.maps.filter((map) => !available.includes(map));
    if (unknown.length > 0) throw new LibraryError("refused", `this texture has no map ${unknown.join(", ")}; it offers ${available.join(", ")}`);
    wanted = [...new Set(request.maps)];
  } else {
    wanted = DEFAULT_MAPS.filter((map) => available.includes(map));
    if (wanted.length === 0) throw new LibraryError("refused", `this texture has none of the PBR maps ${DEFAULT_MAPS.join(", ")}; name maps from ${available.join(", ")}`);
  }
  const out: PlannedFile[] = [];
  const maps: Record<string, string> = {};
  for (const map of wanted) {
    const file = pick(files[map], request.resolution, format, `the ${map} map`);
    const entry = planned(fileNameOf(new URL(file.url)), file);
    out.push(entry);
    maps[map] = entry.path;
  }
  return { files: out, maps };
}

function modelFiles(files: SetFiles, request: PlanRequest, format: string): { files: PlannedFile[]; main: string } {
  const gltf = pick(files["gltf"], request.resolution, format, "this model");
  const main = fileNameOf(new URL(gltf.url));
  const out = [planned(main, gltf)];
  for (const [path, file] of Object.entries(gltf.include ?? {})) out.push(planned(path, file));
  return { files: out, main };
}

function build(type: AssetType, files: AnyFiles, request: PlanRequest): Plan {
  const format = request.format ?? DEFAULT_FORMAT[type];
  if (!FORMATS[type].includes(format)) throw new LibraryError("refused", `a ${type} downloads as ${FORMATS[type].join(" or ")}, not ${format}`);
  let plan: Omit<Plan, "total">;
  if (type === "hdri") {
    const file = pick((files as { hdri: Resolutions }).hdri, request.resolution, format, "this HDRI");
    const main = fileNameOf(new URL(file.url));
    plan = { type, resolution: request.resolution, format, files: [planned(main, file)], main };
  } else if (type === "texture") {
    if (request.maps !== undefined && request.maps.length === 0) throw new LibraryError("refused", "maps must name at least one map");
    plan = { type, resolution: request.resolution, format, ...textureFiles(files as SetFiles, request, format) };
  } else {
    if (request.maps !== undefined) throw new LibraryError("refused", "maps applies only to textures; a model comes with the textures its glTF uses");
    plan = { type, resolution: request.resolution, format, ...modelFiles(files as SetFiles, request, format) };
  }
  const seen = new Set<string>();
  for (const file of plan.files) {
    const key = file.path.toLowerCase();
    if (seen.has(key)) throw new LibraryError("refused", `Poly Haven lists ${file.path} twice for this asset`);
    seen.add(key);
  }
  return { ...plan, total: plan.files.reduce((sum, file) => sum + file.size, 0) };
}

export function planDownload(type: AssetType, files: AnyFiles, request: PlanRequest, maxBytes: number): Plan {
  if (type === "hdri" && request.maps !== undefined) throw new LibraryError("refused", "maps applies only to textures");
  const plan = build(type, files, request);
  if (plan.total <= maxBytes) return plan;
  const fitting = resolutionsOf(type, files).filter((resolution) => {
    try {
      return build(type, files, { ...request, resolution }).total <= maxBytes;
    } catch {
      return false;
    }
  });
  const hint = fitting.length > 0 ? `; ${fitting.join(", ")} fit${fitting.length === 1 ? "s" : ""}` : "; no resolution in this format fits";
  throw new LibraryError(
    "refused",
    `${request.resolution} ${plan.format} is ${megabytes(plan.total)}, above the download cap of ${megabytes(maxBytes)}${hint}`,
  );
}
