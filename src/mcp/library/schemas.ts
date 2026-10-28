import { z } from "zod";
import { ASSET_ID, FORMAT, isAllowedUrl, MD5, RESOLUTION } from "./common.js";

const polyHavenUrl = z.string().max(2048).refine(isAllowedUrl, { message: "is not an https URL on a Poly Haven host" });
const assetId = z.string().regex(ASSET_ID);

export const assetSchema = z.object({
  name: z.string().min(1).max(300),
  type: z.union([z.literal(0), z.literal(1), z.literal(2)]),
  categories: z.array(z.string().max(200)).max(200),
  tags: z.array(z.string().max(200)).max(500),
  authors: z.record(z.string().min(1).max(300), z.string().max(300)),
  max_resolution: z.tuple([z.number().int().positive(), z.number().int().positive()]),
  dimensions: z.array(z.number().nonnegative()).min(2).max(3).optional(),
  thumbnail_url: polyHavenUrl,
  download_count: z.number().int().nonnegative(),
  date_published: z.number().int(),
  description: z.string().max(5000).optional(),
});
export type Asset = z.infer<typeof assetSchema>;

export const listingSchema = z.record(assetId, assetSchema);
export type Listing = z.infer<typeof listingSchema>;

export const categoriesSchema = z.record(z.string().min(1).max(200), z.number().int().nonnegative());

const fileSchema = z.object({
  url: polyHavenUrl,
  size: z.number().int().positive(),
  md5: z.string().regex(MD5),
});

export const remoteFileSchema = fileSchema.extend({
  include: z.record(z.string().min(1).max(400), fileSchema).optional(),
});
export type RemoteFile = z.infer<typeof remoteFileSchema>;

export const resolutionsSchema = z.record(z.string().max(20), z.record(z.string().max(20), z.unknown()));
export type Resolutions = z.infer<typeof resolutionsSchema>;

export const hdriFilesSchema = z.object({ hdri: resolutionsSchema });
export const setFilesSchema = z.record(z.string().regex(/^[A-Za-z0-9_]{1,80}$/), resolutionsSchema);
export type SetFiles = z.infer<typeof setFilesSchema>;

export function describeIssues(error: z.ZodError): string {
  return error.issues
    .slice(0, 3)
    .map((issue) => `${issue.path.length === 0 ? "the response" : issue.path.map(String).join(".")}: ${issue.message}`)
    .join("; ");
}
