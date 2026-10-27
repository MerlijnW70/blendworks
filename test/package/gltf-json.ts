export type Json = Record<string, unknown>;

export function accessor(count: number, min: number[], max: number[], extra: Json = {}): Json {
  return { bufferView: 0, componentType: 5126, count, type: "VEC3", min, max, ...extra };
}

export function scalar(count: number): Json {
  return { bufferView: 0, componentType: 5123, count, type: "SCALAR" };
}

export function document(parts: { nodes: Json[]; meshes?: Json[]; accessors?: Json[]; materials?: Json[]; textures?: Json[]; images?: Json[]; roots?: number[] }): Json {
  return {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: parts.roots ?? [0] }],
    nodes: parts.nodes,
    meshes: parts.meshes ?? [],
    accessors: parts.accessors ?? [],
    materials: parts.materials ?? [],
    textures: parts.textures ?? [],
    images: parts.images ?? [],
  };
}

export function primitive(position: number, indices: number | undefined, material: number | undefined, mode?: number): Json {
  return { attributes: { POSITION: position }, ...(indices === undefined ? {} : { indices }), ...(material === undefined ? {} : { material }), ...(mode === undefined ? {} : { mode }) };
}

export function crate(): Json {
  return document({
    nodes: [
      { name: "Rig", translation: [1, 0, 0], children: [1, 2] },
      { name: "Arm", mesh: 0 },
      { name: "Hand", translation: [0, 2, 0], mesh: 1 },
    ],
    meshes: [{ primitives: [primitive(0, 1, 0)] }, { primitives: [primitive(2, 3, 1)] }],
    accessors: [accessor(8, [-1, -1, -1], [1, 1, 1]), scalar(36), accessor(8, [0, 0, 0], [2, 1, 1]), scalar(18)],
    materials: [
      { name: "steel", pbrMetallicRoughness: { baseColorTexture: { index: 0 } }, normalTexture: { index: 1, texCoord: 1 } },
      { name: "brass", alphaMode: "BLEND", doubleSided: true },
    ],
    textures: [{ source: 0 }, { source: 1 }],
    images: [
      { mimeType: "image/png", bufferView: 0 },
      { mimeType: "image/png", bufferView: 0 },
    ],
  });
}

export function quantisedCrate(): Json {
  return document({
    nodes: [
      { name: "Rig", translation: [1, 0, 0], children: [1, 2] },
      { name: "Arm", children: [3] },
      { name: "Hand", translation: [0, 2, 0], children: [4] },
      { mesh: 0, scale: [0.001, 0.001, 0.001] },
      { mesh: 1, scale: [0.001, 0.001, 0.001], translation: [1, 0.5, 0.5] },
    ],
    meshes: [{ primitives: [primitive(0, 1, 0)] }, { primitives: [primitive(2, 3, 1)] }],
    accessors: [
      accessor(8, [-1000, -1000, -1000], [1000, 1000, 1000], { componentType: 5122 }),
      scalar(36),
      accessor(8, [-1000, -500, -500], [1000, 500, 500], { componentType: 5122 }),
      scalar(18),
    ],
    materials: [
      { name: "steel", pbrMetallicRoughness: { baseColorTexture: { index: 0 } }, normalTexture: { index: 1, texCoord: 1 } },
      { name: "brass", alphaMode: "BLEND", doubleSided: true },
    ],
    textures: [{ source: 0 }, { source: 1 }],
    images: [
      { mimeType: "image/png", bufferView: 0 },
      { mimeType: "image/png", bufferView: 0 },
    ],
  });
}
