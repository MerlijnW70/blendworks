import math

import numpy as np
from mathutils.kdtree import KDTree

from judge_albedo import AlbedoCollector
from judge_common import JudgeError

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
NATURAL_PARTS = ("roughness", "albedo")
ROUGHNESS_SAMPLES = 4096
RADIUS_DIVISOR = 32
FLAT_DEGREES = 3.0
DEGENERATE_DOUBLED_AREA = 2e-12
MAX_LISTED = 64
DIGITS = 4


def natural_parts(text):
    wanted = [item for item in text.split(",") if item]
    unknown = [item for item in wanted if item not in NATURAL_PARTS]
    if unknown:
        raise JudgeError("usage", f"--natural takes {', '.join(NATURAL_PARTS)}, not {', '.join(unknown)}")
    return set(wanted)


def world_vertices(mesh, matrix):
    local = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", local)
    transform = np.array(matrix, dtype=np.float64)
    return local.reshape(-1, 3).astype(np.float64) @ transform[:3, :3].T + transform[:3, 3]


def triangle_corners(mesh):
    corners = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", corners)
    return corners.reshape(-1, 3)


def sample_indices(areas, count):
    cumulative = np.cumsum(areas)
    targets = (np.arange(count, dtype=np.float64) + 0.5) / count * cumulative[-1]
    return np.minimum(np.searchsorted(cumulative, targets, side="right"), len(areas) - 1)


def deviation_angles(centres, doubled_normals, unit_normals, radius, picks):
    tree = KDTree(len(centres))
    for index, centre in enumerate(centres.tolist()):
        tree.insert(centre, index)
    tree.balance()
    angles = {}
    for pick in np.unique(picks).tolist():
        found = [entry[1] for entry in tree.find_range(centres[pick].tolist(), radius)]
        mean = doubled_normals[found].sum(axis=0)
        length = float(np.linalg.norm(mean))
        if length == 0.0:
            angles[pick] = 90.0
            continue
        cosine = float(np.clip(np.dot(unit_normals[pick], mean / length), -1.0, 1.0))
        angles[pick] = math.degrees(math.acos(cosine))
    return np.array([angles[pick] for pick in picks.tolist()], dtype=np.float64)


def object_roughness(world, corners):
    first, second, third = world[corners[:, 0]], world[corners[:, 1]], world[corners[:, 2]]
    doubled_normals = np.cross(second - first, third - first)
    doubled = np.linalg.norm(doubled_normals, axis=1)
    keep = doubled > DEGENERATE_DOUBLED_AREA
    if not keep.any():
        return None
    doubled_normals = doubled_normals[keep]
    doubled = doubled[keep]
    points = np.concatenate([first[keep], second[keep], third[keep]])
    extent = float((points.max(axis=0) - points.min(axis=0)).max())
    radius = extent / RADIUS_DIVISOR
    centres = (first[keep] + second[keep] + third[keep]) / 3.0
    unit_normals = doubled_normals / doubled[:, None]
    picks = sample_indices(doubled / 2.0, ROUGHNESS_SAMPLES)
    angles = deviation_angles(centres, doubled_normals, unit_normals, radius, picks)
    return {
        "faces": int(keep.sum()),
        "samples": ROUGHNESS_SAMPLES,
        "radius": round(radius, 6),
        "p50": round(float(np.percentile(angles, 50)), DIGITS),
        "p90": round(float(np.percentile(angles, 90)), DIGITS),
        "flatShare": round(float(np.mean(angles < FLAT_DEGREES)), DIGITS),
    }


def roughness_result(objects):
    measured = [entry for entry in objects if entry["p90"] is not None]
    return {
        "samplesPerObject": ROUGHNESS_SAMPLES,
        "radiusDivisor": RADIUS_DIVISOR,
        "flatDegrees": FLAT_DEGREES,
        "objects": len(objects),
        "lowestP90": min((entry["p90"] for entry in measured), default=None) if len(measured) == len(objects) else None,
        "highestFlatShare": max((entry["flatShare"] for entry in measured), default=None) if len(measured) == len(objects) else None,
        "items": objects[:MAX_LISTED],
    }


def each_mesh(depsgraph, visit):
    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj.type not in GEOMETRY_TYPES:
            continue
        matrix = instance.matrix_world.copy()
        owner = instance.parent if instance.is_instance and instance.parent is not None else obj
        label = obj.original.name if not instance.is_instance else f"{obj.original.name}@{owner.original.name}"
        mesh = obj.to_mesh()
        try:
            if mesh is None or len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
                continue
            mesh.calc_loop_triangles()
            if len(mesh.loop_triangles) == 0:
                continue
            visit(obj, mesh, matrix, label, obj.data.as_pointer() if obj.data is not None else label)
        finally:
            obj.to_mesh_clear()


def measure_natural(depsgraph, parts):
    objects = []
    albedo = AlbedoCollector() if "albedo" in parts else None

    def visit(obj, mesh, matrix, label, data_key):
        world = world_vertices(mesh, matrix)
        corners = triangle_corners(mesh)
        if "roughness" in parts:
            measured = object_roughness(world, corners)
            entry = {"object": label[:120], "faces": 0, "samples": 0, "radius": None, "p50": None, "p90": None, "flatShare": None}
            objects.append(entry if measured is None else {"object": label[:120], **measured})
        if albedo is not None:
            albedo.add(obj, mesh, world, corners, data_key)

    each_mesh(depsgraph, visit)
    result = {}
    if "roughness" in parts:
        result["surfaceRoughness"] = roughness_result(sorted(objects, key=lambda entry: entry["object"]))
    if albedo is not None:
        result["albedoVariation"] = albedo.result()
    return result
