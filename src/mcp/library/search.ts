import { type AssetType, byResolution, TYPE_BY_NUMBER } from "./common.js";
import type { Asset, Listing, Resolutions, SetFiles } from "./schemas.js";

export interface SearchQuery {
  text?: string;
  categories?: string[];
  tags?: string[];
  page: number;
  perPage: number;
}

export interface Match {
  id: string;
  asset: Asset;
}

export interface SearchPage {
  total: number;
  page: number;
  pages: number;
  matches: Match[];
}

function words(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter((word) => word !== "");
}

function haystack(id: string, asset: Asset): string {
  return [id, asset.name, ...asset.tags, ...asset.categories, asset.description ?? ""].join(" ").toLowerCase();
}

function hasAll(have: string[], wanted: string[] | undefined): boolean {
  if (wanted === undefined || wanted.length === 0) return true;
  const lower = new Set(have.map((entry) => entry.toLowerCase()));
  return wanted.every((entry) => lower.has(entry.toLowerCase()));
}

export function filterListing(listing: Listing, query: SearchQuery): SearchPage {
  const terms = query.text === undefined ? [] : words(query.text);
  const matches = Object.entries(listing)
    .filter(([id, asset]) => {
      if (!hasAll(asset.categories, query.categories) || !hasAll(asset.tags, query.tags)) return false;
      const text = haystack(id, asset);
      return terms.every((term) => text.includes(term));
    })
    .map(([id, asset]) => ({ id, asset }))
    .sort((a, b) => b.asset.download_count - a.asset.download_count || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const pages = Math.max(1, Math.ceil(matches.length / query.perPage));
  const start = (query.page - 1) * query.perPage;
  return { total: matches.length, page: query.page, pages, matches: matches.slice(start, start + query.perPage) };
}

export const NOT_MAPS = new Set(["blend", "gltf", "fbx", "usd", "mtlx"]);

export function resolutionsOf(type: AssetType, files: SetFiles | { hdri: Resolutions }): string[] {
  const found = new Set<string>();
  if (type === "hdri") {
    for (const resolution of Object.keys((files as { hdri: Resolutions }).hdri)) found.add(resolution);
  } else if (type === "model") {
    for (const resolution of Object.keys((files as SetFiles)["gltf"] ?? {})) found.add(resolution);
  } else {
    for (const [map, resolutions] of Object.entries(files as SetFiles)) {
      if (NOT_MAPS.has(map)) continue;
      for (const resolution of Object.keys(resolutions)) found.add(resolution);
    }
  }
  return [...found].sort(byResolution);
}

export function typeOf(asset: Asset): AssetType {
  const type = TYPE_BY_NUMBER[asset.type];
  if (type === undefined) throw new Error(`unknown asset type ${asset.type}`);
  return type;
}

export function dimensionsInMetres(asset: Asset): number[] | undefined {
  return asset.dimensions?.map((millimetres) => Math.round(millimetres) / 1000);
}

export function summary(id: string, asset: Asset, resolutions: string[]): Record<string, unknown> {
  const dimensions = dimensionsInMetres(asset);
  return {
    id,
    name: asset.name,
    type: typeOf(asset),
    categories: asset.categories,
    tags: asset.tags.slice(0, 12),
    ...(dimensions === undefined ? {} : { dimensions_m: dimensions }),
    max_resolution_px: asset.max_resolution,
    resolutions,
  };
}
