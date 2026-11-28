"""Tree skeleton data: checks, chains and preview curve."""

import bpy
import numpy

from .errors import bad_args
from .tree_radii import children_lists, pipe_error

PROPERTY = "blendworks_skeleton"
FORMAT = "blendworks.skeleton"
VERSION = 1
COLUMNS = ("x", "y", "z", "parent", "radius", "order", "kind")
KINDS = ("shoot", "root")


class Skeleton:
    def __init__(self, positions, parents, radii, orders, kinds, exponent, tip_radius, method):
        self.positions = numpy.asarray(positions, dtype=float).reshape(-1, 3)
        self.parents = numpy.asarray(parents, dtype=numpy.int64)
        self.radii = numpy.asarray(radii, dtype=float)
        self.orders = numpy.asarray(orders, dtype=numpy.int64)
        self.kinds = numpy.asarray(kinds, dtype=numpy.int64)
        self.exponent = float(exponent)
        self.tip_radius = float(tip_radius)
        self.method = method

    @property
    def count(self):
        return len(self.parents)

    def to_property(self):
        return {
            "format": FORMAT,
            "version": VERSION,
            "units": "metre",
            "space": "object",
            "up": "z",
            "method": self.method,
            "exponent": self.exponent,
            "tip_radius": self.tip_radius,
            "count": self.count,
            "position": [float(value) for value in self.positions.reshape(-1)],
            "parent": [int(value) for value in self.parents],
            "radius": [float(value) for value in self.radii],
            "order": [int(value) for value in self.orders],
            "kind": [int(value) for value in self.kinds],
        }

    def rows(self, offset, limit):
        end = min(self.count, offset + limit)
        return [
            [round(float(value), 6) for value in self.positions[node]] + [int(self.parents[node]), round(float(self.radii[node]), 7), int(self.orders[node]), int(self.kinds[node])]
            for node in range(offset, end)
        ]

    def page(self, offset, limit):
        end = min(self.count, offset + limit)
        return {"columns": list(COLUMNS), "offset": offset, "limit": limit, "nodes": self.rows(offset, limit), "next_offset": end if end < self.count else None}

    def summary(self):
        children = children_lists(self.parents)
        tips = sum(1 for below in children if not below)
        error, branchings = pipe_error(self.parents, self.radii, self.exponent)
        shoots = self.kinds == 0
        roots = self.kinds == 1
        result = {
            "nodes": self.count,
            "tips": tips,
            "branchings": branchings,
            "root_nodes": int(roots.sum()),
            "max_order": int(self.orders.max()),
            "base_radius": round(float(self.radii[0]), 6),
            "height": round(float(self.positions[shoots, 2].max()), 6),
            "spread": round(float(numpy.hypot(self.positions[:, 0], self.positions[:, 1]).max()), 6),
            "exponent": self.exponent,
            "pipe_error": float(error),
        }
        if roots.any():
            result["root_depth"] = round(float(-self.positions[roots, 2].min() + self.positions[0, 2]), 6)
        return result


def plain(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "to_list"):
        return value.to_list()
    return value


def from_property(obj):
    if PROPERTY not in obj.keys():
        raise bad_args(f"{obj.name} carries no tree skeleton; grow one with grow_tree")
    data = {key: plain(value) for key, value in plain(obj[PROPERTY]).items()}
    if data.get("format") != FORMAT or data.get("version") != VERSION:
        raise bad_args(f"{obj.name} carries a skeleton of format {data.get('format')} version {data.get('version')}; this bridge reads {FORMAT} version {VERSION}")
    count = int(data["count"])
    skeleton = Skeleton(data["position"], data["parent"], data["radius"], data["order"], data["kind"], data["exponent"], data["tip_radius"], data["method"])
    if skeleton.count != count or len(skeleton.positions) != count or len(skeleton.radii) != count or len(skeleton.orders) != count or len(skeleton.kinds) != count:
        raise bad_args(f"the skeleton on {obj.name} has columns of different lengths")
    check_tree(skeleton.parents)
    return skeleton


def check_tree(parents):
    if len(parents) == 0 or parents[0] != -1:
        raise bad_args("a skeleton starts with its root node, whose parent is -1")
    later = numpy.arange(1, len(parents))
    if numpy.any(parents[1:] < 0) or numpy.any(parents[1:] >= later):
        raise bad_args("every node after the root must name an earlier node as its parent")


def chains(skeleton):
    children = children_lists(skeleton.parents)
    found = []
    starts = [(0, None)]
    while starts:
        node, parent = starts.pop()
        chain = [parent, node] if parent is not None else [node]
        while True:
            below = children[node]
            if not below:
                break
            same = [child for child in below if skeleton.orders[child] == skeleton.orders[node] and skeleton.kinds[child] == skeleton.kinds[node]]
            main = same[0] if same else None
            for child in reversed(below):
                if child != main:
                    starts.append((child, node))
            if main is None:
                break
            chain.append(main)
            node = main
        if len(chain) >= 2:
            found.append((chain, parent is not None))
    return found


def preview_curve(name, skeleton, resolution):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_mode = "ROUND"
    curve.bevel_depth = 1.0
    curve.bevel_resolution = resolution
    curve.use_fill_caps = True
    for chain, branched in chains(skeleton):
        spline = curve.splines.new("POLY")
        spline.points.add(len(chain) - 1)
        coordinates = numpy.ones((len(chain), 4))
        coordinates[:, :3] = skeleton.positions[chain]
        radii = skeleton.radii[chain].copy()
        if branched:
            radii[0] = radii[1]
        spline.points.foreach_set("co", coordinates.reshape(-1))
        spline.points.foreach_set("radius", radii)
    return curve
