"""Parses a skeleton from an asset."""

import json

import numpy as np

PROPERTY = "blendworks_skeleton"
FORMAT = "blendworks.skeleton"
VERSION = 1
MAX_NODES = 50000
MAX_TEXT = 16 * 1024 * 1024
COLUMNS = (("position", 3, float), ("parent", 1, int), ("radius", 1, float), ("order", 1, int), ("kind", 1, int))


class SkeletonError(Exception):
    pass


def plain(value):
    if hasattr(value, "to_dict"):
        return {key: plain(item) for key, item in value.to_dict().items()}
    if hasattr(value, "to_list"):
        return value.to_list()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def header(raw):
    if isinstance(raw, str):
        if len(raw) > MAX_TEXT:
            raise SkeletonError(f"the skeleton text is over {MAX_TEXT} characters")
        try:
            raw = json.loads(raw)
        except ValueError:
            raise SkeletonError("the skeleton is not JSON") from None
    if not hasattr(raw, "keys") or not hasattr(raw, "get"):
        raise SkeletonError("the skeleton is not an object")
    if raw.get("format") != FORMAT:
        raise SkeletonError(f"the skeleton's format is not {FORMAT}")
    version = raw.get("version")
    if isinstance(version, bool) or version != VERSION:
        raise SkeletonError(f"the skeleton has version {plain(version)}; the judge reads version {VERSION} only")
    count = raw.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SkeletonError("the skeleton's count must be a positive whole number")
    if count > MAX_NODES:
        raise SkeletonError(f"the skeleton has {count} nodes, over the judge's cap of {MAX_NODES}")
    for key, width, _ in COLUMNS:
        values = raw.get(key)
        if values is None or not hasattr(values, "__len__") or len(values) != width * count:
            raise SkeletonError(f"{key} must hold {width * count} numbers")
    return raw, count


def column(values, kind):
    items = plain(values)
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in items):
        raise SkeletonError("the skeleton's columns must hold numbers")
    array = np.array(items, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise SkeletonError("the skeleton's columns must hold finite numbers")
    if kind is int and not np.all(array == np.round(array)):
        raise SkeletonError("parent, order and kind must be whole numbers")
    return array.astype(np.int64) if kind is int else array


def parse_skeleton(raw):
    raw, count = header(raw)
    data = {key: column(raw.get(key), kind) for key, _, kind in COLUMNS}
    parents = data["parent"]
    if parents[0] != -1 or np.any(parents[1:] < 0) or np.any(parents[1:] >= np.arange(1, count)):
        raise SkeletonError("node 0 must be the only root and every parent an earlier node")
    if np.any(data["radius"] < 0):
        raise SkeletonError("radii must not be negative")
    exponent = plain(raw.get("exponent"))
    return {
        "positions": data["position"].reshape(-1, 3),
        "parents": parents,
        "radii": data["radius"],
        "orders": data["order"],
        "kinds": data["kind"],
        "exponent": float(exponent) if isinstance(exponent, (int, float)) and not isinstance(exponent, bool) and np.isfinite(exponent) else None,
    }
