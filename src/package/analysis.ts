export type Vec3 = [number, number, number];
export type Box = { min: Vec3; max: Vec3 };
export type Matrix = number[];

export const TEXTURE_SLOTS = ["baseColor", "metallicRoughness", "normal", "emissive", "occlusion"] as const;
export type TextureSlot = (typeof TEXTURE_SLOTS)[number];

export type SlotUse = { texCoord: number; image: number | null };

export type MaterialInfo = { name: string; alphaMode: string; doubleSided: boolean; slots: Partial<Record<TextureSlot, SlotUse>> };

export type ImageInfo = { mimeType: string; bufferView: number | null };

export type HolderInfo = { path: string; triangles: number; materials: string[]; localBox: Box | null; worldBox: Box | null };

export type Analysis = {
  holders: HolderInfo[];
  paths: string[];
  matrices: Record<string, Matrix>;
  triangles: number;
  worldBox: Box | null;
  materials: MaterialInfo[];
  images: ImageInfo[];
  extensionsUsed: string[];
  extensionsRequired: string[];
  accessorBytes: number;
};

type Json = Record<string, any>;

const IDENTITY: Matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const NORMALIZED_RANGE: Record<number, number> = { 5120: 127, 5121: 255, 5122: 32767, 5123: 65535 };
const COMPONENT_BYTES: Record<number, number> = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
const TYPE_COMPONENTS: Record<string, number> = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 };
const SLOT_FIELDS: [TextureSlot, (material: Json) => Json | undefined][] = [
  ["baseColor", (material) => material.pbrMetallicRoughness?.baseColorTexture],
  ["metallicRoughness", (material) => material.pbrMetallicRoughness?.metallicRoughnessTexture],
  ["normal", (material) => material.normalTexture],
  ["emissive", (material) => material.emissiveTexture],
  ["occlusion", (material) => material.occlusionTexture],
];

export function multiply(a: Matrix, b: Matrix): Matrix {
  const out = new Array<number>(16).fill(0);
  for (let column = 0; column < 4; column++) {
    for (let row = 0; row < 4; row++) {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += (a[k * 4 + row] ?? 0) * (b[column * 4 + k] ?? 0);
      out[column * 4 + row] = sum;
    }
  }
  return out;
}

export function nodeMatrix(node: Json): Matrix {
  if (Array.isArray(node.matrix) && node.matrix.length === 16) return node.matrix as Matrix;
  const [tx, ty, tz] = (node.translation as number[] | undefined) ?? [0, 0, 0];
  const [qx, qy, qz, qw] = (node.rotation as number[] | undefined) ?? [0, 0, 0, 1];
  const [sx, sy, sz] = (node.scale as number[] | undefined) ?? [1, 1, 1];
  const x2 = qx! + qx!;
  const y2 = qy! + qy!;
  const z2 = qz! + qz!;
  const xx = qx! * x2;
  const xy = qx! * y2;
  const xz = qx! * z2;
  const yy = qy! * y2;
  const yz = qy! * z2;
  const zz = qz! * z2;
  const wx = qw! * x2;
  const wy = qw! * y2;
  const wz = qw! * z2;
  return [
    (1 - (yy + zz)) * sx!, (xy + wz) * sx!, (xz - wy) * sx!, 0,
    (xy - wz) * sy!, (1 - (xx + zz)) * sy!, (yz + wx) * sy!, 0,
    (xz + wy) * sz!, (yz - wx) * sz!, (1 - (xx + yy)) * sz!, 0,
    tx!, ty!, tz!, 1,
  ];
}

function transformPoint(matrix: Matrix, point: Vec3): Vec3 {
  const [x, y, z] = point;
  return [
    (matrix[0] ?? 0) * x + (matrix[4] ?? 0) * y + (matrix[8] ?? 0) * z + (matrix[12] ?? 0),
    (matrix[1] ?? 0) * x + (matrix[5] ?? 0) * y + (matrix[9] ?? 0) * z + (matrix[13] ?? 0),
    (matrix[2] ?? 0) * x + (matrix[6] ?? 0) * y + (matrix[10] ?? 0) * z + (matrix[14] ?? 0),
  ];
}

export function transformBox(matrix: Matrix, box: Box): Box {
  const low: Vec3 = [Infinity, Infinity, Infinity];
  const high: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (let corner = 0; corner < 8; corner++) {
    const point = transformPoint(matrix, [corner & 1 ? box.max[0] : box.min[0], corner & 2 ? box.max[1] : box.min[1], corner & 4 ? box.max[2] : box.min[2]]);
    for (let axis = 0; axis < 3; axis++) {
      low[axis] = Math.min(low[axis]!, point[axis]!);
      high[axis] = Math.max(high[axis]!, point[axis]!);
    }
  }
  return { min: low, max: high };
}

export function mergeBoxes(boxes: Box[]): Box | null {
  if (boxes.length === 0) return null;
  const low: Vec3 = [Infinity, Infinity, Infinity];
  const high: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (const box of boxes) {
    for (let axis = 0; axis < 3; axis++) {
      low[axis] = Math.min(low[axis]!, box.min[axis]!);
      high[axis] = Math.max(high[axis]!, box.max[axis]!);
    }
  }
  return { min: low, max: high };
}

function accessorBox(accessor: Json): Box | null {
  if (!Array.isArray(accessor.min) || !Array.isArray(accessor.max) || accessor.min.length !== 3 || accessor.max.length !== 3) return null;
  const scale = accessor.normalized === true ? NORMALIZED_RANGE[accessor.componentType as number] : undefined;
  const decode = (value: number) => (scale === undefined ? value : Math.max(value / scale, -1));
  return { min: (accessor.min as number[]).map(decode) as Vec3, max: (accessor.max as number[]).map(decode) as Vec3 };
}

function primitiveTriangles(primitive: Json, accessors: Json[]): number {
  const mode = (primitive.mode as number | undefined) ?? 4;
  const count = primitive.indices !== undefined ? accessors[primitive.indices as number]?.count : accessors[primitive.attributes?.POSITION as number]?.count;
  if (typeof count !== "number") return 0;
  if (mode === 4) return Math.floor(count / 3);
  if (mode === 5 || mode === 6) return Math.max(0, count - 2);
  return 0;
}

function meshFacts(mesh: Json, accessors: Json[], materials: Json[]) {
  let triangles = 0;
  const names = new Set<string>();
  const boxes: Box[] = [];
  for (const primitive of (mesh.primitives as Json[] | undefined) ?? []) {
    triangles += primitiveTriangles(primitive, accessors);
    const material = primitive.material === undefined ? undefined : materials[primitive.material as number];
    names.add(material === undefined ? "" : String(material.name ?? `material ${primitive.material}`));
    const box = accessorBox(accessors[primitive.attributes?.POSITION as number] ?? {});
    if (box !== null) boxes.push(box);
  }
  return { triangles, names, box: mergeBoxes(boxes) };
}

function textureImage(texture: Json | undefined): number | null {
  if (texture === undefined) return null;
  const extensions = (texture.extensions ?? {}) as Json;
  const source = texture.source ?? extensions.KHR_texture_basisu?.source ?? extensions.EXT_texture_webp?.source;
  return typeof source === "number" ? source : null;
}

function materialInfo(material: Json, index: number, textures: Json[]): MaterialInfo {
  const slots: MaterialInfo["slots"] = {};
  for (const [slot, pick] of SLOT_FIELDS) {
    const reference = pick(material);
    if (reference === undefined) continue;
    slots[slot] = { texCoord: (reference.texCoord as number | undefined) ?? 0, image: textureImage(textures[reference.index as number]) };
  }
  return { name: String(material.name ?? `material ${index}`), alphaMode: String(material.alphaMode ?? "OPAQUE"), doubleSided: material.doubleSided === true, slots };
}

function accessorBytes(json: Json): number {
  const accessors = (json.accessors as Json[] | undefined) ?? [];
  const used = new Set<number>();
  for (const mesh of (json.meshes as Json[] | undefined) ?? []) {
    for (const primitive of (mesh.primitives as Json[] | undefined) ?? []) {
      if (typeof primitive.indices === "number") used.add(primitive.indices);
      for (const index of Object.values((primitive.attributes ?? {}) as Record<string, number>)) used.add(index);
    }
  }
  let total = 0;
  for (const index of used) {
    const accessor = accessors[index];
    if (accessor === undefined) continue;
    total += (accessor.count as number) * (COMPONENT_BYTES[accessor.componentType as number] ?? 0) * (TYPE_COMPONENTS[accessor.type as string] ?? 0);
  }
  return total;
}

type Visit = { holders: HolderInfo[]; paths: string[]; matrices: Record<string, Matrix> };
type Context = { path: string; relative: Matrix };

function visit(json: Json, index: number, parentWorld: Matrix, context: Context, out: Visit): void {
  const node = (json.nodes as Json[])[index] as Json;
  const local = nodeMatrix(node);
  const world = multiply(parentWorld, local);
  const toAncestor = multiply(context.relative, local);
  const named = typeof node.name === "string" && node.name.length > 0;
  const path = named ? `${context.path}/${node.name}` : context.path;
  const next: Context = named ? { path, relative: IDENTITY } : { path, relative: toAncestor };
  if (named) {
    out.paths.push(path);
    out.matrices[path] = toAncestor;
  }
  if (node.mesh !== undefined) {
    const facts = meshFacts((json.meshes as Json[])[node.mesh as number] as Json, (json.accessors as Json[]) ?? [], (json.materials as Json[]) ?? []);
    const intoHolder = named ? IDENTITY : toAncestor;
    out.holders.push({
      path,
      triangles: facts.triangles,
      materials: [...facts.names].sort(),
      localBox: facts.box === null ? null : transformBox(intoHolder, facts.box),
      worldBox: facts.box === null ? null : transformBox(world, facts.box),
    });
  }
  for (const child of (node.children as number[] | undefined) ?? []) visit(json, child, world, next, out);
}

function mergeHolders(holders: HolderInfo[]): HolderInfo[] {
  const merged = new Map<string, HolderInfo>();
  for (const holder of holders) {
    const existing = merged.get(holder.path);
    if (existing === undefined) {
      merged.set(holder.path, { ...holder, materials: [...holder.materials] });
      continue;
    }
    existing.triangles += holder.triangles;
    existing.materials = [...new Set([...existing.materials, ...holder.materials])].sort();
    const local = mergeBoxes([existing.localBox, holder.localBox].filter((box): box is Box => box !== null));
    const world = mergeBoxes([existing.worldBox, holder.worldBox].filter((box): box is Box => box !== null));
    existing.localBox = local;
    existing.worldBox = world;
  }
  return [...merged.values()].sort((a, b) => a.path.localeCompare(b.path));
}

export function analyse(json: Json): Analysis {
  const scene = (json.scenes as Json[] | undefined)?.[(json.scene as number | undefined) ?? 0];
  const out: Visit = { holders: [], paths: [], matrices: {} };
  for (const root of (scene?.nodes as number[] | undefined) ?? []) visit(json, root, IDENTITY, { path: "", relative: IDENTITY }, out);
  const holders = mergeHolders(out.holders);
  const textures = (json.textures as Json[] | undefined) ?? [];
  return {
    holders,
    paths: out.paths.sort(),
    matrices: out.matrices,
    triangles: holders.reduce((sum, holder) => sum + holder.triangles, 0),
    worldBox: mergeBoxes(holders.flatMap((holder) => (holder.worldBox === null ? [] : [holder.worldBox]))),
    materials: ((json.materials as Json[] | undefined) ?? []).map((material, index) => materialInfo(material, index, textures)),
    images: ((json.images as Json[] | undefined) ?? []).map((image) => ({ mimeType: String(image.mimeType ?? ""), bufferView: typeof image.bufferView === "number" ? image.bufferView : null })),
    extensionsUsed: ((json.extensionsUsed as string[] | undefined) ?? []).slice().sort(),
    extensionsRequired: ((json.extensionsRequired as string[] | undefined) ?? []).slice().sort(),
    accessorBytes: accessorBytes(json),
  };
}
