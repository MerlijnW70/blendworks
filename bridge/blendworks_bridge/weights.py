"""Vertex weights: read, write, smoothing and limiting."""

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_point_line

from .errors import bad_args, not_found


def read_weights(obj, names):
    index_names = {group.index: group.name for group in obj.vertex_groups if group.name in names}
    weights = []
    for vertex in obj.data.vertices:
        entry = {}
        for element in vertex.groups:
            name = index_names.get(element.group)
            if name is not None and element.weight > 0.0:
                entry[name] = element.weight
        weights.append(entry)
    return weights


def write_weights(obj, names, weights):
    groups = {}
    for name in names:
        group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
        group.remove(list(range(len(obj.data.vertices))))
        groups[name] = group
    for index, entry in enumerate(weights):
        for name, weight in entry.items():
            groups[name].add([index], weight, "REPLACE")


def neighbours(mesh):
    linked = [[] for _ in mesh.vertices]
    for edge in mesh.edges:
        first, second = edge.vertices
        linked[first].append(second)
        linked[second].append(first)
    return linked


def smoothed(weights, linked, iterations, factor, locked):
    current = weights
    for _ in range(iterations):
        following = []
        for index, entry in enumerate(current):
            around = linked[index]
            if index in locked or not around:
                following.append(dict(entry))
                continue
            mean = {}
            for other in around:
                for name, weight in current[other].items():
                    mean[name] = mean.get(name, 0.0) + weight / len(around)
            names = set(entry) | set(mean)
            blended = {name: (1.0 - factor) * entry.get(name, 0.0) + factor * mean.get(name, 0.0) for name in names}
            following.append({name: weight for name, weight in blended.items() if weight > 1e-6})
        current = following
    return current


def limited(weights, most):
    result = []
    for entry in weights:
        if len(entry) > most:
            kept = sorted(entry.items(), key=lambda item: (-item[1], item[0]))[:most]
            entry = dict(kept)
        result.append(entry)
    return result


def normalized(weights):
    result = []
    for entry in weights:
        total = sum(entry.values())
        result.append({name: weight / total for name, weight in entry.items()} if total > 0 else entry)
    return result


def islands(mesh):
    linked = neighbours(mesh)
    label = [-1] * len(mesh.vertices)
    count = 0
    for start in range(len(mesh.vertices)):
        if label[start] >= 0:
            continue
        label[start] = count
        stack = [start]
        while stack:
            current = stack.pop()
            for other in linked[current]:
                if label[other] < 0:
                    label[other] = count
                    stack.append(other)
        count += 1
    return label, count


def segments(armature, names):
    matrix = armature.matrix_world
    return [(name, matrix @ armature.data.bones[name].head_local, matrix @ armature.data.bones[name].tail_local) for name in names]


def distance_to_segment(point, head, tail):
    closest, along = intersect_point_line(point, head, tail)
    if along <= 0.0:
        closest = head
    elif along >= 1.0:
        closest = tail
    return (point - closest).length


def nearest_bone(point, bone_segments):
    return min(bone_segments, key=lambda item: (distance_to_segment(point, item[1], item[2]), item[0]))[0]


def region_vertices(obj, entry, labels):
    mesh = obj.data
    chosen = [key for key in ("vertex_group", "island", "near") if key in entry]
    if len(chosen) != 1:
        raise bad_args(f"rigid part for {entry['bone']} needs exactly one of vertex_group, island or near")
    if "vertex_group" in entry:
        group = obj.vertex_groups.get(entry["vertex_group"])
        if group is None:
            raise not_found(f"{obj.name} has no vertex group named {entry['vertex_group']}")
        return {vertex.index for vertex in mesh.vertices if any(element.group == group.index and element.weight > 0 for element in vertex.groups)}
    if "island" in entry:
        found = {index for index, label in enumerate(labels) if label == entry["island"]}
        if not found:
            raise bad_args(f"{obj.name} has no loose part {entry['island']}")
        return found
    point = obj.matrix_world.inverted() @ Vector(entry["near"])
    polygons = [list(polygon.vertices) for polygon in mesh.polygons]
    if not polygons:
        raise bad_args(f"{obj.name} has no faces to find a part near {list(entry['near'])}")
    tree = BVHTree.FromPolygons([vertex.co for vertex in mesh.vertices], polygons)
    _, _, face, _ = tree.find_nearest(point)
    part = labels[polygons[face][0]]
    return {index for index, label in enumerate(labels) if label == part}


def whole_parts(weights, labels, count):
    totals = [dict() for _ in range(count)]
    for index, entry in enumerate(weights):
        bucket = totals[labels[index]]
        for name, weight in entry.items():
            bucket[name] = bucket.get(name, 0.0) + weight
    dominant = [max(bucket.items(), key=lambda item: (item[1], item[0]))[0] if bucket else None for bucket in totals]
    return [{dominant[labels[index]]: 1.0} if dominant[labels[index]] else dict(entry) for index, entry in enumerate(weights)]


def influence_counts(weights):
    return max((len(entry) for entry in weights), default=0), sum(1 for entry in weights if not entry)
