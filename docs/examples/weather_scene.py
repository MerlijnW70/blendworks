import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import bpy
import numpy

from blendworks_bridge import Handler

sys.path.insert(0, HERE)
import to_the_horizon

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "weather-scene"))
WEATHERS = (ARGS[1] if len(ARGS) > 1 else "clear,fair_cumulus,overcast,heavy_rain,thunderstorm").split(",")
TIMES = (ARGS[2] if len(ARGS) > 2 else "noon,golden_hour").split(",")
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "900"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "256"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
BUDGET = int(os.environ.get("BLENDWORKS_COVER_BUDGET", "1500000"))
FORM = os.environ.get("BLENDWORKS_CLOUD_FORM", "auto")
NEAR = 100.0
FAR = 6000.0
TREE = [-6.0, 25.0]
WALL = ([-24.0, 9.0], [6.0, 19.0])
CAMERA = ([3.0, -4.0, 1.55], [-5.0, 20.0, 4.5])
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


def terrain():
    cmd("heightfield", name="meadow", size=[NEAR, NEAR], resolution=201, height=0.9, seed=9, scale=30.0, octaves=5, hurst=0.75, attributes=["slope", "height"])
    cmd("transform", name="meadow", location=[-NEAR / 2.0, -NEAR / 2.0 + 15.0, 0.0])
    cmd("heightfield", name="plain", size=[FAR, FAR], resolution=121, height=0.25, base_height=-1.4, seed=4, scale=400.0, octaves=3, hurst=0.6)
    cmd("transform", name="plain", location=[-FAR / 2.0, -FAR / 2.0, 0.0])
    cmd("material_procedural", name="meadow_ground", grass_ground={"density": 0.7, "dryness": 0.3})
    cmd("assign_material", name="meadow", material="meadow_ground")
    cmd("assign_material", name="plain", material="meadow_ground")


def heights():
    obj = bpy.data.objects["meadow"]
    world = numpy.array([list(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])
    return world


def ground_height(points, x, y):
    nearest = numpy.argmin(numpy.linalg.norm(points[:, :2] - [x, y], axis=1))
    return float(points[nearest, 2])


def stones():
    cmd("material_procedural", name="wall_stone", stone={"color": [0.3, 0.29, 0.26], "secondary_color": [0.18, 0.18, 0.16], "cracks": False})
    variants = []
    for index, size in enumerate(([0.5, 0.3, 0.22], [0.42, 0.34, 0.2], [0.6, 0.28, 0.24], [0.36, 0.3, 0.26])):
        name = f"stone_{index}"
        cmd("add_primitive", type="cube", name=name, size=1.0, location=[0.0, -80.0 - 3.0 * index, 0.0])
        cmd("transform", name=name, scale=size)
        cmd("apply_transform", name=name, scale=True)
        cmd("chip", name=name, count=7, depth=0.35 * min(size), seed=11 + index)
        cmd("abrade", name=name, amount=0.6, seed=index, edge_length=0.06)
        cmd("noise_displace", name=name, amplitude=0.015, seed=3 + index, scale=0.12, octaves=3, hurst=0.5)
        cmd("shade_smooth", name=name)
        cmd("assign_material", name=name, material="wall_stone")
        variants.append(name)
    return variants


def wall(variants, points):
    generator = random.Random(7)
    (x0, y0), (x1, y1) = WALL
    length = math.hypot(x1 - x0, y1 - y0)
    heading = math.degrees(math.atan2(y1 - y0, x1 - x0))
    per_variant = {name: ([], [], []) for name in variants}
    for course in range(4):
        travelled = 0.21 * (course % 2)
        while travelled < length:
            share = travelled / length
            x, y = x0 + share * (x1 - x0), y0 + share * (y1 - y0)
            for row in (-0.22, 0.22):
                if course == 3 and row > 0:
                    continue
                name = generator.choice(variants)
                nx, ny = -math.sin(math.radians(heading)), math.cos(math.radians(heading))
                inset = 0.05 * course
                px = x + nx * row * (1.0 - inset * 2)
                py = y + ny * row * (1.0 - inset * 2)
                z = ground_height(points, px, py) - 0.05 + 0.2 * course + generator.uniform(-0.02, 0.02)
                spots, turns, sizes = per_variant[name]
                spots.append([px, py, z])
                turns.append([generator.uniform(-6, 6), generator.uniform(-6, 6), heading + generator.uniform(-12, 12)])
                sizes.append(generator.uniform(0.85, 1.15))
            travelled += 0.44 + generator.uniform(-0.04, 0.06)
    parts = []
    for name, (spots, turns, sizes) in per_variant.items():
        if spots:
            cmd("instances", source=name, points=spots, rotations=turns, scales=sizes, realize=True, name=f"wall_{name}")
            parts.append(f"wall_{name}")
    cmd("delete", names=variants)
    return parts


def tree(points):
    base = [TREE[0], TREE[1], ground_height(points, *TREE) - 0.1]
    extra = {"points": max(200, int(6000 * DETAIL))} if DETAIL < 1.0 else {}
    cmd("grow_tree", name="oak", preset="oak", seed=3, location=base, limit=0, **extra)
    cmd("tree_mesh", name="oak")
    cmd("tree_leaves", name="oak_bark", leaves_name="oak_leaves", seed=3, **({"detail": "low"} if DETAIL < 1.0 else {}))


def build():
    cmd("new_scene")
    terrain()
    points = heights()
    parts = wall(stones(), points)
    tree(points)
    location, target = CAMERA
    location = [location[0], location[1], ground_height(points, location[0], location[1]) + location[2]]
    cmd("add_camera", name="eye", location=location, target=target, lens=28.0)
    cmd("ground_cover", target="meadow", preset="meadow", camera="eye", near=12.0, budget=BUDGET, obstacles=parts + ["oak_bark"], trees=["oak_bark"], seed=5)
    if to_the_horizon.enabled():
        to_the_horizon.surround(cmd, ["plain"], "eye", species=("oak", "maple", "birch"), haze=False)
    cmd("save_blend", path="weather-scene.blend")


def shoot(weather, time_of_day):
    cmd("load_blend", path="weather-scene.blend")
    report = cmd("weather", preset=weather, time_of_day=time_of_day, form=FORM, seed=2)
    cmd("camera_setup", name="eye", view_transform="AgX", look="base_contrast")
    final = cmd("render_final", path=f"{weather}-{time_of_day}.png", camera="eye", width=WIDTH, height=HEIGHT, samples=SAMPLES, time_limit=SECONDS, device=DEVICE, preview=False)
    return {"weather": {key: report[key] for key in ("storm", "sun", "lamp", "cover", "rain", "lightning", "exposure", "cost")},
            "samples": final["samples"], "time": final["time_budget"], "clouds": final["clouds"]}


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    if not os.path.exists(os.path.join(OUT, "weather-scene.blend")):
        build()
    shots = {f"{weather}-{time_of_day}": shoot(weather, time_of_day) for weather in WEATHERS for time_of_day in TIMES}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"shots": shots, "commands": LOG}, handle, indent=1)


if __name__ == "__main__":
    main()
