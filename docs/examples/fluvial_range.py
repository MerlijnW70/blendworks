"""A 61 km young alpine range from fluvial_terrain, rendered with render_final at its defaults: a clay hillshade from above and an oblique view at eye level.

Run: blender -b --factory-startup --python docs/examples/fluvial_range.py -- <output folder>
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import numpy

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "fluvial-range"))
SIZE_KM = float(os.environ.get("BLENDWORKS_FLUVIAL_SIZE", "61.41"))
CELL = float(os.environ.get("BLENDWORKS_FLUVIAL_CELL", "30"))
EYE = 1.7
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3)})
    return reply["result"]


def wall_distance(heights, cell, row, column, rise=150.0, reach=3000.0):
    """Distance from a valley floor cell to the nearest ground rising more than rise above it, within reach."""
    span = int(reach / cell)
    rows = slice(max(0, row - span), row + span + 1)
    columns = slice(max(0, column - span), column + span + 1)
    window = heights[rows, columns]
    wall_rows, wall_columns = numpy.nonzero(window > heights[row, column] + rise)
    if wall_rows.size == 0:
        return reach
    return float(numpy.hypot(wall_rows + rows.start - row, wall_columns + columns.start - column).min() * cell)


def valley_view(river, heights, cell, least=1000.0, ahead=5000.0):
    """A camera EYE metres above the floor of the main valley where its walls stand farthest away (at least least
    metres when the valley allows), looking ahead metres up-valley at a point a third of the way up the walls."""
    cells = [(int(round(y / cell)), int(round(x / cell))) for x, y, _ in river]
    distances = [wall_distance(heights, cell, row, column) for row, column in cells]
    best = int(numpy.argmax(distances))
    row, column = cells[best]
    floor = float(heights[row, column])
    along = numpy.cumsum(numpy.r_[0.0, numpy.hypot(*numpy.diff(river[:, :2], axis=0).T)])
    upstream = int(numpy.searchsorted(along, max(along[best] - ahead, 0.0)))
    look = river[min(upstream, best)]
    window = heights[max(0, row - 100): row + 101, max(0, column - 100): column + 101]
    target_height = floor + (float(window.max()) - floor) / 3.0
    return [float(river[best][0]), float(river[best][1]), floor + EYE], [float(look[0]), float(look[1]), target_height]


def main():
    built = cmd("fluvial_terrain", name="Range", preset="young_alpine", size=SIZE_KM, cell=CELL, path="range.npz")
    extent = built["extent_km"] * 1000.0
    grids = numpy.load(os.path.join(OUT, "range.npz"))
    heights, cell = grids["height"], float(grids["cell"])
    cmd("add_light", type="sun", name="Sun", rotation=[45.0, 0.0, 225.0], energy=4.0)
    top = float(heights.max()) + 5000.0
    cmd("add_camera", name="Above", location=[extent / 2.0, extent / 2.0, top], rotation=[0.0, 0.0, 0.0], orthographic_scale=extent)
    cmd("render_final", path="hillshade_top.png", camera="Above")
    eye, target = valley_view(numpy.array(built["rivers"][0]["points"]), heights, cell)
    cmd("delete", names=["Sun"])
    cmd("sky", sun={"elevation": 30.0, "azimuth": 135.0})
    cmd("add_camera", name="Eye", location=eye, target=target, lens=24.0, active=False)
    cmd("render_final", path="oblique_eye.png", camera="Eye")
    report = {"measures": built["measures"], "rivers": len(built["rivers"]), "lakes": len(built["lakes"]), "log": LOG}
    with open(os.path.join(OUT, "fluvial_range.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({key: report["measures"][key] for key in ("seconds", "trunk_order", "hack_exponent", "hack_decades", "undrained_pits", "aspect_east_share")}))


main()
