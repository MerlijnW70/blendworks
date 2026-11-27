import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import bpy
import numpy

from blendworks_bridge import Handler
from blendworks_bridge.limits import MAX_COVER_INSTANCES

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "liquid-lake"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "900"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "256"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
BUDGET = int(os.environ.get("BLENDWORKS_COVER_BUDGET", str(min(5_000_000, MAX_COVER_INSTANCES))))
COVER_NEAR = 120.0
TREES = int(os.environ.get("BLENDWORKS_TREES", "6"))
FORM = os.environ.get("BLENDWORKS_CLOUD_FORM", "auto")
SEED = int(os.environ.get("BLENDWORKS_TERRAIN_SEED", "3"))
LAND_RESOLUTION = int(os.environ.get("BLENDWORKS_LAND_RESOLUTION", "301"))
SHOTS = os.environ.get("BLENDWORKS_SHOTS", "lake,rocks").split(",")
TILE = 300.0
SHIFT = 4.5 * TILE
ROLLING = {"height": 9.0, "scale": 180.0, "octaves": 5, "hurst": 0.8}
HILLS = {"amplitude": 100.0, "seed": 260, "scale": 2500.0, "octaves": 3, "hurst": 0.5}
RIVER_WIDTH = 4.0
RIVER_DEPTH = 0.6
RIVER_TRIALS = int(os.environ.get("BLENDWORKS_RIVER_TRIALS", "6"))
RINGS = ((TILE, range(3, 6), 101, 4.0), (3.0 * TILE, range(0, 3), 91, 10.0), (9.0 * TILE, range(-1, 2), 55, 40.0))
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


def attempt(name, /, **args):
    reply = HANDLER.handle({"cmd": name, "args": args})
    LOG.append({"cmd": name, "seconds": 0.0, "ok": reply["ok"]})
    return reply["result"] if reply["ok"] else None


def tile(name, size, index, resolution, skirt):
    """One heightfield tile of the shared noise, raised by the shared hills; both sample the same world points in every
    tile, so tiles of any size meet."""
    extra = {"skirt": True, "skirt_depth": skirt} if skirt else {}
    cmd("heightfield", name=name, size=[size, size], tile=list(index), resolution=resolution, seed=SEED, **ROLLING, **extra)
    cmd("transform", name=name, location=[index[0] * size - SHIFT, index[1] * size - SHIFT, 0.0])
    cmd("noise_displace", name=name, direction="z", **HILLS)
    cmd("assign_material", name=name, material="ground")


def terrain():
    """Rolling land around the lake in a broad valley, hills to the horizon: a 300 m tile at full detail inside three rings
    of coarser tiles out to 4 km. Each ring's tiles are three times the size of the last, so with the shift of 1350 m every
    ring stays centred on the land; skirts close the small steps where a coarse tile meets a finer one."""
    cmd("material_procedural", name="ground", grass_ground={"density": 0.75, "dryness": 0.2})
    tile("land", TILE, (4, 4), LAND_RESOLUTION, None)
    for size, indices, resolution, skirt in RINGS:
        centre = (indices.start + indices.stop - 1) // 2
        for i in indices:
            for j in indices:
                if (i, j) != (centre, centre):
                    tile(f"ground_{int(size)}_{i}_{j}", size, (i, j), resolution, skirt)


def points():
    obj = bpy.data.objects["land"]
    return numpy.array([list(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices])


def lake(heights):
    inner = heights[(numpy.abs(heights[:, 0]) < TILE * 0.3) & (numpy.abs(heights[:, 1]) < TILE * 0.3)]
    lowest = inner[numpy.argmin(inner[:, 2])]
    return cmd("liquid_body", kind="lake", name="lake", ground=["land"], point=[float(lowest[0]), float(lowest[1]), 0.0], seed=3)


def river(heights, lake_report):
    level = lake_report["level"]
    centre = numpy.array(lake_report["centre"])
    ring = heights[(heights[:, 2] > level + 2.0) & (numpy.abs(heights[:, 0]) < TILE * 0.45) & (numpy.abs(heights[:, 1]) < TILE * 0.45)]
    reach = numpy.hypot(ring[:, 0] - centre[0], ring[:, 1] - centre[1])
    ring, reach = ring[reach > 45.0], reach[reach > 45.0]
    order = numpy.argsort(-reach)
    found = []
    for index in order[: 8000: 40]:
        source = [float(ring[index][0]), float(ring[index][1]), 0.0]
        trial = attempt("liquid_body", kind="river", name="river", ground=["land"], point=source, width=RIVER_WIDTH, depth=RIVER_DEPTH, carve=False, wet_shore=False)
        if trial is None:
            continue
        cmd("delete", names=["river"])
        if trial["joins"] == "water" and trial["length"] > 80.0:
            found.append((trial["mean_speed"], source))
            if len(found) == RIVER_TRIALS:
                break
    if not found:
        raise RuntimeError("no source drains into the lake; try another BLENDWORKS_TERRAIN_SEED")
    _, source = min(found)
    return cmd("liquid_body", kind="river", name="river", ground=["land"], point=source, width=RIVER_WIDTH, depth=RIVER_DEPTH, seed=5)


def rocks():
    """Boulders along the water line of the lake and the river banks: lumpy, chipped and worn, granite grey with lichen on
    top, 0.3 to 1.5 m with a few larger, partly standing in the shallows and wet where the water reaches."""
    cmd("material_procedural", name="rock", stone={"color": [0.2, 0.19, 0.175], "secondary_color": [0.1, 0.095, 0.088], "cell_scale": 2.5, "cracks": False, "roughness": 0.8})
    cmd("material_layer", material="rock", mask="up_facing", moss={}, amount=0.2, softness=0.5, seed=4)
    variants = []
    for index, size in enumerate(([1.0, 0.8, 0.6], [1.2, 0.75, 0.55], [0.8, 0.7, 0.65], [1.1, 0.9, 0.5])):
        name = f"rock_{index}"
        cmd("add_primitive", type="ico_sphere", name=name, radius=0.5, subdivisions=1, location=[0.0, 0.0, 0.5 * size[2]], rotation=[0.0, 0.0, 17.0 * index])
        cmd("transform", name=name, scale=size)
        cmd("apply_transform", name=name, location=True, rotation=True, scale=True)
        cmd("chip", name=name, count=6, depth=0.12, seed=31 + index)
        cmd("abrade", name=name, amount=0.7, seed=index, edge_length=0.04)
        cmd("noise_displace", name=name, amplitude=0.04, seed=7 + index, scale=0.5, octaves=4, hurst=0.6)
        cmd("shade_smooth", name=name)
        cmd("uv_smart_project", name=name)
        cmd("assign_material", name=name, material="rock")
        variants.append(name)
    placed = cmd("scatter", target="land", sources=[{"name": name, "weight": 1.0} for name in variants], min_distance=0.6,
                 density_mask=["shore", "noise"], shore_width=2.5, shore_depth=0.3, shore_wet=0.6,
                 noise={"scale": 18.0, "octaves": 2, "threshold": 0.3, "softness": 0.25, "seed": 9},
                 scale_range=[0.3, 2.2], scale_distribution="power", scale_exponent=-2.2, embed=0.25, align="blend", align_factor=0.3,
                 seed=4, name="shore_rocks", realize=True, max_count=900)
    cmd("delete", names=variants)
    return placed


def trees(heights, level, mouth):
    """Trees on dry ground near where the river meets the lake, where the main shot looks."""
    planted = []
    generator = numpy.random.default_rng(6)
    near = numpy.hypot(heights[:, 0] - mouth[0], heights[:, 1] - mouth[1])
    dry = heights[(heights[:, 2] > level + 1.5) & (near > 12.0) & (near < 70.0)]
    species = ["oak", "willow", "birch", "maple", "oak", "pine"]
    chosen = []
    for spot in dry[generator.permutation(len(dry))]:
        if all(math.hypot(spot[0] - other[0], spot[1] - other[1]) > 14.0 for other in chosen):
            chosen.append(spot)
        if len(chosen) == TREES:
            break
    for index, spot in enumerate(chosen):
        name = f"tree_{index}"
        cmd("grow_tree", name=name, preset=species[index % len(species)], seed=10 + index, location=[float(spot[0]), float(spot[1]), float(spot[2]) - 0.1], limit=0)
        cmd("tree_mesh", name=name)
        cmd("tree_leaves", name=f"{name}_bark", leaves_name=f"{name}_leaves", seed=10 + index, **({"detail": "low"} if DETAIL < 1.0 else {}))
        planted.append(f"{name}_bark")
    return planted


def ground_at(heights, x, y):
    return float(heights[numpy.argmin(numpy.hypot(heights[:, 0] - x, heights[:, 1] - y)), 2])


def rock_points(placed):
    names = placed.get("objects") or [placed["name"]]
    found = []
    for name in names:
        obj = bpy.data.objects[name]
        local = numpy.zeros(len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get("co", local)
        matrix = numpy.array(obj.matrix_world)
        found.append(local.reshape(-1, 3)[::25] @ matrix[:3, :3].T + matrix[:3, 3])
    return numpy.concatenate(found)


def cameras(heights, lake_report, mouth, placed):
    """The main shot stands on a rise of the land, the lake between it and the river mouth, so the lake, the mouth, the
    rocks on its banks, the trees near it and the hills behind are in one frame: of the spots 90 to 170 m from the mouth
    inside the land, the one whose line to the mouth passes closest to the lake's centre. The second shot stands at the
    water line by the rocks nearest the mouth, looking along them over the lake."""
    level = lake_report["level"]
    centre = numpy.array(lake_report["centre"])
    best = None
    for distance in (90.0, 110.0, 130.0, 150.0, 170.0):
        for angle in numpy.radians(numpy.arange(0.0, 360.0, 5.0)):
            spot = mouth[:2] + distance * numpy.array([math.cos(angle), math.sin(angle)])
            if numpy.abs(spot).max() > TILE / 2.0 - 25.0 or ground_at(heights, *spot) < level + 2.0:
                continue
            ahead = (mouth[:2] - spot) / distance
            miss = abs(float(numpy.cross(ahead, centre - spot)))
            if best is None or miss < best[0]:
                best = (miss, spot)
    spot = best[1]
    ahead = (mouth[:2] - spot) / numpy.linalg.norm(mouth[:2] - spot)
    location = [float(spot[0]), float(spot[1]), ground_at(heights, *spot) + 12.0]
    target = [float(0.5 * (mouth[0] + centre[0])), float(0.5 * (mouth[1] + centre[1])), level]
    cmd("add_camera", name="eye", location=location, target=target, lens=26.0)
    cmd("camera_setup", name="eye", view_transform="AgX", look="base_contrast")
    rocks = rock_points(placed)
    shore = rocks[numpy.abs(rocks[:, 2] - level) < 0.8]
    rock = shore[numpy.argmin(numpy.hypot(shore[:, 0] - mouth[0], shore[:, 1] - mouth[1]))]
    outward = (rock[:2] - centre) / numpy.linalg.norm(rock[:2] - centre)
    stand = rock[:2] + outward * 7.0
    look = [float(rock[0] - outward[0] * 4.0), float(rock[1] - outward[1] * 4.0), level + 0.3]
    cmd("add_camera", name="shore", location=[float(stand[0]), float(stand[1]), ground_at(heights, *stand) + 1.6], target=look, lens=32.0)
    cmd("camera_setup", name="shore", view_transform="AgX", look="base_contrast")
    return ["eye", "shore"]


def water_line_distances(placed):
    """How far rock vertices lie from the water: positive above the water line, negative under it."""
    from blendworks_bridge import liquid_world

    water = liquid_world.Water(liquid_world.liquid_objects(bpy.context.scene))
    return -water.signed_depth(rock_points(placed), 100.0)


def build():
    cmd("new_scene")
    terrain()
    cmd("weather", preset="fair_cumulus", time_of_day="afternoon", form=FORM, seed=2, haze=False)
    heights = points()
    report = lake(heights)
    water = heights[numpy.abs(heights[:, 2] - report["level"]) < 0.5]
    report["centre"] = [float(numpy.median(water[:, 0])), float(numpy.median(water[:, 1]))]
    flow = river(heights, report)
    mouth = numpy.array(flow["path"][-1])
    heights = points()
    placed = rocks()
    planted = trees(heights, report["level"], mouth)
    shots = cameras(heights, report, mouth, placed)
    obstacles = placed.get("objects") or [placed["name"]]
    reeds = [{"name": "reeds", "element": "sedge", "density": 25.0, "liquid": "shore", "shore": 1.2, "clumping": {"radius": 0.6, "per_clump": 12.0}}]
    cmd("ground_cover", target="land", preset="meadow", cameras=shots, near=COVER_NEAR, view_only=True, budget=BUDGET, obstacles=obstacles + planted, trees=planted, seed=5, populations=reeds)
    cmd("atmosphere", visibility=10000.0, height_falloff=300.0)
    cmd("save_blend", path="liquid-lake.blend")
    return report, flow, placed, shots


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    lake_report, river_report, placed, shots = build()
    distances = water_line_distances(placed)
    renders = {}
    for shot, path, key in (("eye", "lake.png", "lake"), ("shore", "rocks.png", "rocks")):
        if key in SHOTS:
            renders[shot] = cmd("render_final", path=path, camera=shot, width=WIDTH, height=HEIGHT, samples=SAMPLES, time_limit=SECONDS, device=DEVICE, preview=False)
    final = renders.get("eye") or next(iter(renders.values()))
    summary = {
        "lake": {key: lake_report[key] for key in ("level", "area", "volume", "max_depth", "wind", "waves", "shore")},
        "river": {key: river_report[key] for key in ("length", "mean_speed", "joins", "carved_vertices")},
        "rocks": {"count": placed["count"], "objects": placed.get("objects") or [placed["name"]], "wet": placed.get("wet"),
                  "highest_above_water": round(float(distances.max()), 4), "deepest_under_water": round(float(-distances.min()), 4)},
        "cameras": shots,
        "render": {key: final[key] for key in ("samples", "time_budget", "liquids", "clouds", "atmosphere")},
        "commands": LOG,
    }
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1, default=str)


if __name__ == "__main__":
    main()
