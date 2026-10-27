import numpy as np

import bpy

from judge_textures import material_maps

MAX_SIDE = 2048
ALPHA_INSIDE = 0.5
LUMINANCE = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)
CANDIDATES_PER_CHUNK = 4_000_000
EDGE_SLACK = 1e-9
MAX_LISTED = 64
DIGITS = 6


def base_colour_images(material, cache):
    if material is None:
        return ()
    key = material.as_pointer()
    if key not in cache:
        cache[key] = tuple(sorted(material_maps(material).get("baseColor", ()), key=lambda image: image.name))
    return cache[key]


def triangle_materials(obj, mesh):
    indices = np.empty(len(mesh.loop_triangles), dtype=np.int32)
    mesh.loop_triangles.foreach_get("material_index", indices)
    slots = obj.material_slots
    materials = []
    for index in range(max(len(slots), len(mesh.materials), 1)):
        material = None
        if index < len(slots) and slots[index].material is not None:
            material = slots[index].material
        elif index < len(mesh.materials):
            material = mesh.materials[index]
        materials.append(material)
    return indices, materials


def triangle_uvs(mesh):
    layer = mesh.uv_layers.active
    if layer is None:
        return None
    uvs = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    layer.uv.foreach_get("vector", uvs)
    loops = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    return uvs.reshape(-1, 2).astype(np.float64)[loops].reshape(-1, 3, 2)


def spans(texel_corners):
    low = np.ceil(texel_corners.min(axis=1) - 0.5).astype(np.int64)
    high = np.floor(texel_corners.max(axis=1) - 0.5).astype(np.int64)
    return low, high


def inside_triangles(points_x, points_y, corners):
    (ax, ay), (bx, by), (cx, cy) = (corners[:, index, :].T for index in range(3))

    def edge(x0, y0, x1, y1):
        return (x1 - x0)[:, None, None] * (points_y - y0[:, None, None]) - (y1 - y0)[:, None, None] * (points_x - x0[:, None, None])

    first, second, third = edge(ax, ay, bx, by), edge(bx, by, cx, cy), edge(cx, cy, ax, ay)
    positive = (first >= -EDGE_SLACK) & (second >= -EDGE_SLACK) & (third >= -EDGE_SLACK)
    negative = (first <= EDGE_SLACK) & (second <= EDGE_SLACK) & (third <= EDGE_SLACK)
    return positive | negative


def rasterize(mask, width, height, uv_triangles):
    if len(uv_triangles) == 0:
        return
    scaled = uv_triangles * np.array([width, height], dtype=np.float64)
    finite = np.isfinite(scaled).all(axis=(1, 2))
    scaled = scaled[finite]
    doubled = np.abs((scaled[:, 1, 0] - scaled[:, 0, 0]) * (scaled[:, 2, 1] - scaled[:, 0, 1]) - (scaled[:, 1, 1] - scaled[:, 0, 1]) * (scaled[:, 2, 0] - scaled[:, 0, 0]))
    scaled = scaled[doubled > 0]
    if len(scaled) == 0:
        return
    shift = np.floor(scaled.min(axis=1) / np.array([width, height])) * np.array([width, height])
    local = scaled - shift[:, None, :]
    low, high = spans(local)
    extent = np.maximum(high - low + 1, 1).max(axis=1)
    sides = 2 ** np.ceil(np.log2(extent)).astype(np.int64)
    for side in np.unique(sides).tolist():
        chosen = np.nonzero(sides == side)[0]
        per_chunk = max(1, CANDIDATES_PER_CHUNK // (side * side))
        offsets = np.arange(side, dtype=np.int64)
        for start in range(0, len(chosen), per_chunk):
            group = chosen[start : start + per_chunk]
            xs = low[group, 0][:, None] + offsets[None, :]
            ys = low[group, 1][:, None] + offsets[None, :]
            points_x = np.broadcast_to(xs[:, None, :] + 0.5, (len(group), side, side))
            points_y = np.broadcast_to(ys[:, :, None] + 0.5, (len(group), side, side))
            hit = inside_triangles(points_x, points_y, local[group])
            hit &= (xs[:, None, :] <= high[group, 0][:, None, None]) & (ys[:, :, None] <= high[group, 1][:, None, None])
            if not hit.any():
                continue
            which, row, column = np.nonzero(hit)
            texel_x = np.mod(xs[which, column], width)
            texel_y = np.mod(ys[which, row], height)
            mask[texel_y * width + texel_x] = True


def image_pixels(image):
    width, height = (int(value) for value in image.size[:])
    if width == 0 or height == 0:
        return None
    source = image
    if max(width, height) > MAX_SIDE:
        factor = MAX_SIDE / max(width, height)
        width, height = max(1, round(width * factor)), max(1, round(height * factor))
        source = image.copy()
        source.scale(width, height)
    try:
        channels = source.channels
        pixels = np.empty(width * height * channels, dtype=np.float32)
        source.pixels.foreach_get(pixels)
    finally:
        if source is not image:
            bpy.data.images.remove(source)
    return width, height, pixels.reshape(-1, channels).astype(np.float64)


class AlbedoCollector:
    def __init__(self):
        self.images = {}
        self.materials = {}
        self.seen = set()
        self.surface = 0.0
        self.untextured = 0.0

    def add(self, obj, mesh, world, corners, data_key):
        if data_key in self.seen:
            return
        self.seen.add(data_key)
        first, second, third = world[corners[:, 0]], world[corners[:, 1]], world[corners[:, 2]]
        areas = np.linalg.norm(np.cross(second - first, third - first), axis=1) / 2.0
        self.surface += float(areas.sum())
        uvs = triangle_uvs(mesh)
        indices, materials = triangle_materials(obj, mesh)
        for slot, material in enumerate(materials):
            chosen = np.nonzero(np.clip(indices, 0, len(materials) - 1) == slot)[0]
            if len(chosen) == 0:
                continue
            images = base_colour_images(material, self.materials)
            if not images or uvs is None:
                self.untextured += float(areas[chosen].sum())
                continue
            for image in images:
                entry = self.images.setdefault(image.as_pointer(), {"image": image, "triangles": []})
                entry["triangles"].append(uvs[chosen])

    def image_texels(self, entry):
        loaded = image_pixels(entry["image"])
        if loaded is None:
            return None, None
        width, height, pixels = loaded
        mask = np.zeros(width * height, dtype=bool)
        triangles = np.unique(np.concatenate(entry["triangles"]).reshape(-1, 6), axis=0).reshape(-1, 3, 2)
        rasterize(mask, width, height, triangles)
        if pixels.shape[1] >= 4:
            mask &= pixels[:, 3] >= ALPHA_INSIDE
        colours = pixels[:, :3] if pixels.shape[1] >= 3 else np.repeat(pixels[:, :1], 3, axis=1)
        return (width, height), colours[mask] @ LUMINANCE

    def result(self):
        listed = []
        pooled = []
        for entry in sorted(self.images.values(), key=lambda item: item["image"].name):
            size, luminance = self.image_texels(entry)
            record = {"image": entry["image"].name[:120], "size": None if size is None else list(size), "texels": 0, "mean": None, "cv": None}
            if luminance is not None and len(luminance) > 0:
                mean = float(luminance.mean())
                record.update({"texels": int(len(luminance)), "mean": round(mean, DIGITS), "cv": round(float(luminance.std()) / mean, DIGITS) if mean > 0 else None})
                pooled.append(luminance)
            listed.append(record)
        values = np.concatenate(pooled) if pooled else np.empty(0)
        mean = float(values.mean()) if len(values) > 0 else 0.0
        cv = round(float(values.std()) / mean, DIGITS) if len(values) > 0 and mean > 0 else None
        return {
            "cv": cv,
            "texels": int(len(values)),
            "mean": round(mean, DIGITS) if len(values) > 0 else None,
            "images": listed[:MAX_LISTED],
            "untexturedShare": round(self.untextured / self.surface, DIGITS) if self.surface > 0 else None,
        }
