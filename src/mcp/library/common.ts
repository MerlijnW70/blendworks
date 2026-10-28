export const API_BASE = "https://api.polyhaven.com";
export const ALLOWED_HOSTS: ReadonlySet<string> = new Set(["api.polyhaven.com", "dl.polyhaven.org", "cdn.polyhaven.com"]);
export const LICENSE = "CC0-1.0";
export const LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/";
export const LIBRARY_FOLDER = "library";

export type LibraryErrorCode = "offline" | "refused" | "invalid" | "not_found" | "failed" | "cancelled";

export class LibraryError extends Error {
  constructor(
    readonly code: LibraryErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "LibraryError";
  }
}

export const ASSET_TYPES = ["hdri", "texture", "model"] as const;
export type AssetType = (typeof ASSET_TYPES)[number];

export const API_TYPE_NAMES: Record<AssetType, string> = { hdri: "hdris", texture: "textures", model: "models" };
export const TYPE_BY_NUMBER: Record<number, AssetType> = { 0: "hdri", 1: "texture", 2: "model" };

export const ASSET_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
export const RESOLUTION = /^[1-9][0-9]?k$/;
export const FORMAT = /^[a-z0-9]{1,10}$/;
export const MD5 = /^[0-9a-f]{32}$/;
const PATH_SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9._ -]{0,199}$/;

export function checkAssetId(id: unknown): string {
  if (typeof id !== "string" || !ASSET_ID.test(id)) {
    throw new LibraryError("refused", `${JSON.stringify(id)} is not a Poly Haven asset id; ids are letters, digits, "_" and "-", such as "abandoned_parking"`);
  }
  return id;
}

export function resolutionValue(resolution: string): number {
  return Number(resolution.slice(0, -1));
}

export function byResolution(a: string, b: string): number {
  return resolutionValue(a) - resolutionValue(b);
}

export function checkedUrl(raw: string, base?: URL): URL {
  let url: URL;
  try {
    url = base === undefined ? new URL(raw) : new URL(raw, base);
  } catch {
    throw new LibraryError("refused", `${JSON.stringify(raw.slice(0, 200))} is not a URL`);
  }
  if (url.protocol !== "https:" || url.username !== "" || url.password !== "" || url.port !== "") {
    throw new LibraryError("refused", `${url.href.slice(0, 200)} is not a plain https URL on a Poly Haven host`);
  }
  if (!ALLOWED_HOSTS.has(url.hostname)) {
    throw new LibraryError("refused", `${url.hostname} is not a Poly Haven host; only ${[...ALLOWED_HOSTS].join(", ")} are fetched`);
  }
  return url;
}

export function isAllowedUrl(raw: string): boolean {
  try {
    checkedUrl(raw);
    return true;
  } catch {
    return false;
  }
}

export function checkRelativePath(path: string): string {
  const segments = path.split("/");
  if (path.includes("\\") || path.includes("\0") || segments.some((segment) => !PATH_SEGMENT.test(segment) || segment.endsWith(".") || segment.endsWith(" "))) {
    throw new LibraryError("refused", `${JSON.stringify(path.slice(0, 200))} is not a safe file path inside an asset folder`);
  }
  return path;
}

export function fileNameOf(url: URL): string {
  const last = url.pathname.split("/").pop() ?? "";
  let name: string;
  try {
    name = decodeURIComponent(last);
  } catch {
    throw new LibraryError("refused", `${url.href.slice(0, 200)} has no usable file name`);
  }
  return checkRelativePath(name);
}

export function megabytes(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}
