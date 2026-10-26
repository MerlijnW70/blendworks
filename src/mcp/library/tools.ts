import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { ASSET_ID, ASSET_TYPES, RESOLUTION } from "./common.js";
import { FORMATS } from "./plan.js";

export const LIBRARY_PREFIX = "library_";
export const MAX_PER_PAGE = 24;
export const DEFAULT_PER_PAGE = 10;
export const MIN_PREVIEW = 64;
export const MAX_PREVIEW = 512;
export const DEFAULT_PREVIEW = 256;

const allFormats = [...new Set(Object.values(FORMATS).flat())];
const id = z.string().regex(ASSET_ID, 'is not a Poly Haven asset id (letters, digits, "_" and "-")');
const type = z.enum(ASSET_TYPES);
const label = z.string().min(1).max(100);

export const searchArgs = z.strictObject({
  type: type.optional(),
  query: z.string().min(1).max(200).optional(),
  category: label.optional(),
  tags: z.array(label).min(1).max(10).optional(),
  page: z.number().int().min(1).max(1000).default(1),
  per_page: z.number().int().min(1).max(MAX_PER_PAGE).default(DEFAULT_PER_PAGE),
});

export const previewArgs = z.strictObject({
  id,
  size: z.number().int().min(MIN_PREVIEW).max(MAX_PREVIEW).default(DEFAULT_PREVIEW),
});

export const downloadArgs = z.strictObject({
  id,
  resolution: z.string().regex(RESOLUTION, 'is not a resolution such as "1k", "2k" or "4k"'),
  format: z.enum(allFormats as [string, ...string[]]).optional(),
  maps: z.array(z.string().regex(/^[A-Za-z0-9_]{1,80}$/)).min(1).max(16).optional(),
});

export const applyArgs = z.strictObject({
  id,
  type: type.optional(),
  object: z.string().min(1).max(256).optional(),
  material: z.string().min(1).max(256).optional(),
  strength: z.number().min(0).max(100).optional(),
  rotation: z.number().min(-360).max(360).optional(),
});

const idProperty = { type: "string", description: 'Poly Haven asset id, such as "abandoned_parking".', pattern: ASSET_ID.source, maxLength: 80 };
const typeProperty = { type: "string", enum: [...ASSET_TYPES] };

export const LIBRARY_TOOLS: Tool[] = [
  {
    name: "library_search",
    description:
      "Search Poly Haven's free CC0 library: HDRIs (lighting), scanned PBR textures, and models. Returns id, name, type, categories, dimensions in metres and the resolutions on offer.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        type: { ...typeProperty, description: "Asset type. Default: all three." },
        query: { type: "string", description: "Words that must all appear in the id, name, tags, categories or description.", minLength: 1, maxLength: 200 },
        category: { type: "string", description: 'A Poly Haven category, such as "outdoor" or "studio" for HDRIs, or "wood" for textures.', minLength: 1, maxLength: 100 },
        tags: { type: "array", description: "Tags that must all be present.", items: { type: "string", minLength: 1, maxLength: 100 }, minItems: 1, maxItems: 10 },
        page: { type: "integer", description: "Page number, from 1.", minimum: 1, maximum: 1000, default: 1 },
        per_page: { type: "integer", description: "Results per page.", minimum: 1, maximum: MAX_PER_PAGE, default: DEFAULT_PER_PAGE },
      },
    },
    annotations: { title: "Search Poly Haven", readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "library_preview",
    description: "Show a Poly Haven asset's thumbnail as an image, to judge it before downloading.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["id"],
      properties: {
        id: idProperty,
        size: { type: "integer", description: "Thumbnail width and height in pixels.", minimum: MIN_PREVIEW, maximum: MAX_PREVIEW, default: DEFAULT_PREVIEW },
      },
    },
    annotations: { title: "Preview a Poly Haven asset", readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "library_download",
    description:
      "Download a Poly Haven asset into library/<type>/<id>/ in the workspace, md5-checked and all-or-nothing, with a LICENSE.json record. HDRI: one .hdr or .exr. Texture: the PBR map set. Model: the glTF with its textures.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["id", "resolution"],
      properties: {
        id: idProperty,
        resolution: { type: "string", description: 'Resolution from library_search, such as "1k", "2k" or "4k".', pattern: RESOLUTION.source, maxLength: 3 },
        format: { type: "string", description: "HDRI: hdr (default) or exr. Texture: jpg (default), png or exr. Model: gltf.", enum: allFormats },
        maps: {
          type: "array",
          description: "Texture maps to fetch, by Poly Haven name. Default: Diffuse, nor_gl, Rough, Metal, AO, Displacement and Mask, where present.",
          items: { type: "string", pattern: "^[A-Za-z0-9_]{1,80}$" },
          minItems: 1,
          maxItems: 16,
        },
      },
    },
    annotations: { title: "Download a Poly Haven asset", readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  },
  {
    name: "library_apply",
    description:
      "Use a downloaded asset in the scene: import a model, set an HDRI as the world lighting, or build a PBR material from a texture set (needs blender_material_pbr). Works offline.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["id"],
      properties: {
        id: idProperty,
        type: { ...typeProperty, description: "Asset type; needed only when the id is downloaded as more than one type." },
        object: { type: "string", description: "Texture: object to give the material.", minLength: 1, maxLength: 256 },
        material: { type: "string", description: "Texture: material name. Default: the asset id.", minLength: 1, maxLength: 256 },
        strength: { type: "number", description: "HDRI: environment strength (default 1).", minimum: 0, maximum: 100 },
        rotation: { type: "number", description: "HDRI: turn about Z in degrees (default 0).", minimum: -360, maximum: 360 },
      },
    },
    annotations: { title: "Apply a downloaded asset", readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
];

export function describeArgsError(error: z.ZodError): string {
  return error.issues
    .slice(0, 3)
    .map((issue) => {
      const where = issue.path.length === 0 ? "the arguments" : issue.path.map(String).join(".");
      return `${where}: ${issue.message}`;
    })
    .join("; ");
}
