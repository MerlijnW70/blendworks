"""The woodland of the lake example, laid out by rules from the scene: a forest on the far bank whose edge faces the lake
across the river mouth, copses scattered over the dry land around the lake, a hedgerow along a field edge that runs away
from the viewer, and with the horizon option the patches of the distant forest carried on into the land. A camera
stands in the open in front of the forest edge. The canopy the woodland writes (meadow_canopy) feeds the meadow fields'
shade, which thins the grass and flowers of the meadow preset and grows moss under the trees."""
import os

import bpy
import numpy
from mathutils.kdtree import KDTree

VARIANTS = int(os.environ.get("BLENDWORKS_TREE_VARIANTS", "2"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
PARALLEL = os.environ.get("BLENDWORKS_TREE_PARALLEL", "1") != "0"
FOREST_RIM = 30.0
FOREST_DEPTH = 300.0
FOREST_HALF = 130.0
FOREST_SLANT = 70.0
SUN_PENALTY = 6.0
LAND_MARGIN = 10.0
RIM_WANDER = 8.0
RIM_WAVELENGTH = 60.0
COPSE_AREA = 140.0
COPSES = 5
COPSE_RADIUS = 11.0
HEDGE_SIDE = 60.0
HEDGE_LENGTH = 240.0
EDGE_STAND_OFF = 24.0
EDGE_INSIDE = 20.0
RIM_STEP = 5.0


def frame(eye, mouth):
    ahead = numpy.asarray(mouth[:2], dtype=float) - numpy.asarray(eye[:2], dtype=float)
    ahead /= numpy.linalg.norm(ahead)
    return ahead, numpy.array([-ahead[1], ahead[0]])


def forest_outline(eye, mouth):
    """The far-bank forest: its rim faces the lake across the river mouth, slanted so the edge is seen in depth."""
    ahead, side = frame(eye, mouth)
    rim = numpy.asarray(mouth[:2], dtype=float) + ahead * FOREST_RIM
    far = rim + ahead * FOREST_DEPTH
    near_corner, far_corner = rim - side * FOREST_HALF, rim + side * FOREST_HALF + ahead * FOREST_SLANT
    return [near_corner, far_corner, far + side * FOREST_HALF, far - side * FOREST_HALF]


def stands(eye, mouth, centre, field):
    ahead, side = frame(eye, mouth)
    outline = forest_outline(eye, mouth)
    start = numpy.asarray(eye[:2], dtype=float) + side * HEDGE_SIDE
    line = [start, start + ahead * 0.5 * HEDGE_LENGTH + side * 8.0, start + ahead * HEDGE_LENGTH + side * 22.0]
    found = [
        {"kind": "forest", "outline": [[float(x), float(y)] for x, y in outline]},
        {"kind": "copses", "centre": [float(centre[0]), float(centre[1])], "radius": COPSE_AREA, "count": COPSES, "copse_radius": COPSE_RADIUS},
        {"kind": "hedgerow", "line": [[float(x), float(y)] for x, y in line]},
    ]
    if field:
        found.append({"kind": "forest", "field": field})
    return found


def grow(cmd, tiles, eye, mouth, centre, field=None, seed=7):
    return cmd("woodland", name="Woodland", ground=list(tiles), stands=stands(eye, mouth, centre, field), variants=VARIANTS,
               points_share=min(1.0, DETAIL), detail="full" if DETAIL >= 1.0 else "low", rim_wander=RIM_WANDER, rim_wavelength=RIM_WAVELENGTH,
               parallel=PARALLEL, seed=seed)


def canopy_points(name="land"):
    obj = bpy.data.objects[name]
    count = len(obj.data.vertices)
    local = numpy.zeros(count * 3, dtype=numpy.float32)
    obj.data.vertices.foreach_get("co", local)
    values = numpy.zeros(count, dtype=numpy.float32)
    obj.data.attributes["meadow_canopy"].data.foreach_get("value", values)
    points = local.reshape(-1, 3) + numpy.array(obj.matrix_world.translation)
    return points, values


def edge_camera(cmd, level, eye, mouth, tiles):
    """A close view of the forest edge, placed from the forest stand's own outline: along every side of the outline,
    every RIM_STEP metres, a stand point EDGE_STAND_OFF metres out along the side's outward normal, kept where it is on
    the land the ground cover covers, in the open (no canopy) and dry, and where the forest behind the rim, on any
    tile, has closed canopy. Of
    those, the highest, so the camera stands clear of the mist on the low ground by the water, less SUN_PENALTY metres
    for each unit it looks into the sun, so the edge is seen in light. The camera looks back along the normal."""
    outline = numpy.array(forest_outline(eye, mouth))
    middle = outline.mean(axis=0)
    land, _ = canopy_points("land")
    low, high = land[:, :2].min(axis=0) + LAND_MARGIN, land[:, :2].max(axis=0) - LAND_MARGIN
    parts = [canopy_points(name) for name in tiles]
    points, values = numpy.concatenate([part[0] for part in parts]), numpy.concatenate([part[1] for part in parts])
    suns = [obj for obj in bpy.context.scene.objects if obj.type == "LIGHT" and obj.data.type == "SUN"]
    toward_sun = numpy.array(suns[0].matrix_world.to_3x3().col[2])[:2] if suns else numpy.zeros(2)
    tree = KDTree(len(points))
    for index, (x, y, _) in enumerate(points.tolist()):
        tree.insert((x, y, 0.0), index)
    tree.balance()

    def nearest(point):
        return tree.find((float(point[0]), float(point[1]), 0.0))[1]

    best = None
    refused = {"off_land": 0, "covered": 0, "low": 0, "no_forest": 0}
    for corner in range(len(outline)):
        start, end = outline[corner], outline[(corner + 1) % len(outline)]
        along = end - start
        length = float(numpy.linalg.norm(along))
        normal = numpy.array([along[1], -along[0]]) / length
        if normal @ (start - middle) < 0.0:
            normal = -normal
        for distance in numpy.arange(RIM_STEP, length - RIM_STEP, RIM_STEP):
            rim = start + along * distance / length
            stand = rim + normal * EDGE_STAND_OFF
            inside = rim - normal * EDGE_INSIDE
            if numpy.any(stand < low) or numpy.any(stand > high):
                refused["off_land"] += 1
                continue
            here = nearest(stand)
            z = float(points[here, 2])
            reason = "covered" if values[here] > 0.02 else "low" if z < level + 1.0 else "no_forest" if values[nearest(inside)] < 0.6 else None
            if reason:
                refused[reason] += 1
                continue
            score = z + SUN_PENALTY * float(normal @ toward_sun)
            if best is None or score > best[0]:
                best = (score, stand, normal, z)
    if best is None:
        raise RuntimeError(f"no open, dry ground faces the forest edge: {refused}")
    _, stand, normal, z = best
    target = stand - normal * (EDGE_STAND_OFF + 6.0)
    cmd("add_camera", name="edge", location=[float(stand[0]), float(stand[1]), z + 1.6], target=[float(target[0]), float(target[1]), z + 3.5], lens=28.0)
    return "edge"


def summary(result):
    keep = ("plants", "classes", "class_shares", "regularity", "clustering", "species", "budget")
    report = {key: result[key] for key in keep}
    report["layers"] = {key: value["count"] for key, value in result["layers"].items()}
    report["stands"] = [{key: stand[key] for key in ("kind", "area", "counts")} for stand in result["stands"]]
    report["canopy"] = {name: entry["covered_share"] for name, entry in result["canopy"]["ground"].items() if entry["covered_share"] > 0.0}
    return report

