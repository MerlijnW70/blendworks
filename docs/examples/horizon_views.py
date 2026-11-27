"""Two views to the horizon built only with Blendworks commands. valley: a long valley floor of meadow, the camera low at
one end looking along it, distant land in the ranges style rising on both sides and behind each other ahead, forest on
the slopes and mist on the floor. hill: a rounded hill in rolling land, the camera on its top looking over rolling land
and forest to a flat horizon. Run: blender -b --factory-startup --python docs/examples/horizon_views.py -- out valley"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import numpy

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "horizon-views"))
VIEWS = (ARGS[1] if len(ARGS) > 1 else "valley,hill").split(",")
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "900"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "128"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
TREES = float(os.environ.get("BLENDWORKS_HORIZON_TREES", "0.3"))
LAND_DETAIL = int(os.environ.get("BLENDWORKS_HORIZON_DETAIL", "160"))
FRAMES = int(os.environ.get("BLENDWORKS_HORIZON_FRAMES", "8"))
FRAME_PIXELS = int(os.environ.get("BLENDWORKS_HORIZON_PIXELS", "96"))
HANDLER = None
LOG = []


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3)})
    print(f"ok {name} {LOG[-1]['seconds']} s", flush=True)
    return reply["result"]


def ground_at(name, x, y):
    import bpy
    from mathutils import Vector

    obj = bpy.data.objects[name]
    hit, location, *_ = obj.ray_cast(obj.matrix_world.inverted() @ Vector((x, y, 10_000.0)), Vector((0.0, 0.0, -1.0)))
    if not hit:
        raise RuntimeError(f"no ground under {x}, {y}")
    return (obj.matrix_world @ location).z


def meadow(name, size, height, scale, seed):
    cmd("heightfield", name=name, size=size, resolution=241, height=height, seed=seed, scale=scale, octaves=5, hurst=0.75)
    cmd("transform", name=name, location=[-size[0] / 2.0, -size[1] / 2.0, 0.0])
    cmd("material_procedural", name="meadow", grass_ground={"density": 0.75, "dryness": 0.25})
    cmd("assign_material", name=name, material="meadow")
    cmd("shade_smooth", name=name)


def valley():
    meadow("floor", [1400.0, 6000.0], 6.0, 220.0, 4)
    z = ground_at("floor", 0.0, -2700.0)
    cmd("add_camera", name="eye", location=[0.0, -2700.0, z + 6.0], target=[0.0, 4000.0, z + 120.0], lens=30.0)
    cmd("camera_setup", name="eye", view_transform="AgX", look="base_contrast")
    cmd("weather", preset="fair_cumulus", time_of_day="morning", form="sheet", seed=3, haze=False)
    land = cmd("distant_land", terrain=["floor"], style="ranges", range_height=1600.0, camera="eye", detail=LAND_DETAIL, seed=7)
    forest = cmd("distant_forest", land=land["name"], species=["pine", "birch"], tree_detail=TREES, cover=0.55, max_slope=38.0, seed=7, frames=FRAMES, frame_pixels=FRAME_PIXELS)
    mist = cmd("valley_mist", ground=["floor", land["name"]], radius=4000.0, thickness=12.0, fade=10.0, visibility=600.0, valley_width=400.0)
    haze = cmd("atmosphere", visibility=30_000.0, height_falloff=1500.0, method="depth")
    return {"land": land, "forest": forest, "mist": mist, "haze": haze}


def dome(name, side, cells, height, width):
    xs = numpy.linspace(-side / 2.0, side / 2.0, cells)
    grid_x, grid_y = numpy.meshgrid(xs, xs)
    z = height * numpy.exp(-(grid_x ** 2 + grid_y ** 2) / width ** 2)
    vertices = numpy.column_stack([grid_x.ravel(), grid_y.ravel(), z.ravel()]).tolist()
    faces = [[row * cells + column, row * cells + column + 1, (row + 1) * cells + column + 1, (row + 1) * cells + column]
             for row in range(cells - 1) for column in range(cells - 1)]
    cmd("mesh_from_data", name=name, vertices=vertices, faces=faces)


def hill():
    dome("hill", 2400.0, 241, 160.0, 700.0)
    cmd("noise_displace", name="hill", direction="z", amplitude=14.0, seed=12, scale=260.0, octaves=4, hurst=0.7)
    cmd("material_procedural", name="meadow", grass_ground={"density": 0.92, "dryness": 0.3})
    cmd("assign_material", name="hill", material="meadow")
    cmd("shade_smooth", name="hill")
    x, y = 0.0, -150.0
    z = ground_at("hill", x, y)
    heading = math.radians(-60.0)
    cmd("add_camera", name="eye", location=[x, y, z + 3.0], target=[x + 3000.0 * math.cos(heading), y + 3000.0 * math.sin(heading), z - 330.0], lens=28.0)
    cmd("camera_setup", name="eye", view_transform="AgX", look="base_contrast")
    cmd("weather", preset="fair_cumulus", time_of_day="afternoon", form="sheet", seed=5, haze=False)
    land = cmd("distant_land", terrain=["hill"], style="rolling", camera="eye", detail=LAND_DETAIL, seed=3)
    forest = cmd("distant_forest", land=land["name"], species=["oak", "maple", "birch"], tree_detail=TREES, cover=0.4, seed=3, frames=FRAMES, frame_pixels=FRAME_PIXELS)
    haze = cmd("atmosphere", visibility=35_000.0, height_falloff=1500.0, method="depth")
    return {"land": land, "forest": forest, "haze": haze}


def summary_of(built):
    land, forest = built["land"], built["forest"]
    return {"land": {key: land[key] for key in ("triangles", "rings", "border", "statistics", "curvature")},
            "forest": {key: forest[key] for key in ("counts", "cover", "switches", "calibration")},
            "haze": {key: built["haze"][key] for key in ("visibility", "method")}}


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    shots = {}
    for view in VIEWS:
        cmd("new_scene")
        built = {"valley": valley, "hill": hill}[view]()
        final = cmd("render_final", path=f"{view}.png", camera="eye", width=WIDTH, height=HEIGHT, samples=SAMPLES,
                    time_limit=SECONDS, device=DEVICE, preview=False)
        shots[view] = dict(summary_of(built), render={key: final[key] for key in ("samples", "time_budget", "atmosphere")})
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"shots": shots, "commands": LOG}, handle, indent=1, default=str)


if __name__ == "__main__":
    main()
