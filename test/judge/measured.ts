import type { Measurements } from "../../src/judge/measurements.js";
import type { AssetRecord } from "../../src/judge/report.js";
import type { Isolation } from "../../src/judge/sandbox.js";

export const CRATE_MEASUREMENTS: Measurements = {
  format: "glb",
  fileBytes: 2784,
  triangles: 12,
  visibleTriangles: 12,
  objects: 1,
  objectsAll: 1,
  bounds: { min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0.8] },
  size: [1, 1, 0.8],
  origin: { point: [0, 0, 0], source: "object Crate", bottomCentreDistance: 0, centreDistance: 0.4 },
  manifold: { nonManifoldEdges: 0, boundaryEdges: 0, wireEdges: 0, nonManifoldVertices: 0, looseVertices: 0, looseParts: 1 },
  shells: { count: 1, closed: 1, inverted: 0 },
  faces: { degenerate: 0, duplicate: 0, hiddenRatio: 0, hiddenFaces: 0, tested: 12, sampled: false },
  materials: { count: 2, names: ["metal", "wood"] },
  uv: { present: true, meshesWithoutUv: 0, coverage: 0.375, overlap: 0, outsideUnitSquare: 0 },
  unitScale: 1,
  externalFilesRefused: [],
  references: { files: 0, unresolved: [] },
};

export function assetRecord(path: string, bytes: number | null = 1): AssetRecord {
  return { path, sha256: null, bytes, files: [], setSha256: null, setBytes: null };
}

export function isolation(memory: string, platform = "linux"): Isolation {
  return { network: "isolated", memory, timeoutMs: 300_000, platform, filesystem: "mount namespace", processes: "own PID namespace" };
}
