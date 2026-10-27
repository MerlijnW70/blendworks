import { basename, extname, join } from "node:path";
import type { Delivery } from "../judge/delivery.js";
import type { DeviceMode } from "../judge/device.js";
import type { Report } from "../judge/report.js";
import type { AssetSpec } from "../judge/spec.js";
import type { Sandbox } from "../judge/stages.js";
import { runPackage } from "./pipeline.js";
import { packageResults } from "./rules.js";

type Draft = Omit<Report, "summary">;

export type PackageStageOptions = { preview?: boolean; device?: DeviceMode; backends?: readonly string[]; renderTimeoutMs?: number };

export function packageStem(name: string | undefined, assetPath: string): string {
  const raw = name ?? basename(assetPath, extname(assetPath));
  const clean = raw.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return clean.length > 0 ? clean.slice(0, 60) : "asset";
}

export async function packageStage(draft: Draft, spec: AssetSpec, delivery: Delivery, sandbox: Sandbox, outDir: string, maxTriangles: number, options: PackageStageOptions): Promise<void> {
  draft.package = null;
  const report = await runPackage(
    { ...(spec.lods === undefined ? {} : { lods: spec.lods }), ...(spec.package === undefined ? {} : { package: spec.package }), ...(spec.views === undefined ? {} : { views: spec.views }) },
    {
      assetPath: delivery.main,
      outDir: join(outDir, "package"),
      sandbox,
      stem: packageStem(spec.name, delivery.main),
      maxTriangles,
      ...(options.device === undefined ? {} : { device: options.device }),
      ...(options.backends === undefined ? {} : { backends: options.backends }),
      ...(options.renderTimeoutMs === undefined ? {} : { renderTimeoutMs: options.renderTimeoutMs }),
      ...(draft.measurements === null ? {} : { deliveredTriangles: draft.measurements.triangles }),
      ...(options.preview === undefined ? {} : { preview: options.preview }),
    },
  );
  draft.package = report;
  draft.rules.push(...packageResults(spec, report));
}
