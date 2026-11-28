import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

import bpy
import numpy

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "meadow-cover"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
RESOLUTION = int(os.environ.get("BLENDWORKS_TERRAIN_RESOLUTION", "161"))
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
BUDGET = int(os.environ.get("BLENDWORKS_COVER_BUDGET", "800000"))
TILE = 40.0
TREE = [20.0, 24.0, 0.0]
EYE = ([15.5, 9.0, 0.9], [20.0, 22.0, 0.6])
WIDE = ([6.0, 2.0, 5.0], [21.0, 22.0, 1.0])
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []
KEYS = ("count", "budget", "budget_factor", "triangles", "surface_area", "skipped", "instances", "bytes")


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    entry.update({key: result[key] for key in KEYS if key in result})
    if name == "ground_cover":
        entry["populations"] = {item["name"]: item["count"] for item in result["populations"]}
        entry["near"] = result["falloff"]["near"]
        entry["contact_mean"] = result["contact"]["mean"]
    LOG.append(entry)
    return result


def terrain():
    cmd("heightfield", name="ground", size=[TILE, TILE], resolution=RESOLUTION, height=1.4, seed=9, scale=22.0, octaves=5, hurst=0.75, attributes=["slope", "height"])
    cmd("material_procedural", name="meadow_ground", grass_ground={"density": 0.6, "dryness": 0.35})
    cmd("assign_material", name="ground", material="meadow_ground")


def ground_height(x, y):
    obj = bpy.data.objects["ground"]
    points = numpy.array([list(vertex.co) for vertex in obj.data.vertices])
    nearest = numpy.argmin(numpy.linalg.norm(points[:, :2] - [x, y], axis=1))
    return float(points[nearest, 2])


def tree():
    base = [TREE[0], TREE[1], ground_height(TREE[0], TREE[1]) - 0.05]
    cmd("grow_tree", name="oak", preset="gnarled_oak", seed=3, points=max(200, int(4000 * DETAIL)), location=base, limit=0)
    cmd("material_procedural", name="bark", bark={"grain": "y", "coordinates": "uv", "fissure_spacing": 0.035, "bump": 12.0})
    cmd("material_procedural", name="leaf", leaf={"cutout": True})
    cmd("tree_mesh", name="oak", bark_material="bark", wood_material="bark", root_material="bark", flare={"amount": 0.7, "lobes": 0.8})
    cmd("tree_leaves", name="oak_bark", leaves_name="oak_leaves", material="leaf", size=0.26, density=max(1.0, 12.0 * DETAIL), tip_leaves=5, orders=2, seed=3)


def rocks():
    cmd("material_procedural", name="rock", stone={"color": [0.4, 0.38, 0.35], "secondary_color": [0.25, 0.24, 0.22], "cracks": False})
    for variant in range(3):
        name = f"rock_{variant}"
        cmd("add_primitive", type="ico_sphere", name=name, radius=0.6, subdivisions=4, location=[-50.0 - 5.0 * variant, 0.0, 0.0])
        cmd("transform", name=name, scale=[1.0 + 0.2 * variant, 1.0, 0.65])
        cmd("apply_transform", name=name, scale=True)
        cmd("noise_displace", name=name, amplitude=0.18, seed=3 + variant, mode="billow", scale=1.2, octaves=3, hurst=0.9)
        cmd("noise_displace", name=name, amplitude=0.02, seed=9 + variant, scale=0.2, octaves=3, hurst=0.5)
        cmd("shade_smooth", name=name)
        cmd("set_origin", name=name, to="bottom_centre")
        cmd("assign_material", name=name, material="rock")
    cmd("scatter", target="ground", sources=[{"name": f"rock_{variant}"} for variant in range(3)], min_distance=2.5, max_count=14, scale_range=[0.6, 2.0], scale_distribution="power", embed=0.3, align="blend", align_factor=0.5, seed=4, name="rocks")
    for variant in range(3):
        cmd("delete", names=[f"rock_{variant}"])


def cameras():
    for name, (location, target) in (("eye", EYE), ("wide", WIDE)):
        cmd("add_camera", name=name, location=location)
        cmd("look_at", name=name, point=target)
    cmd("set_world", color=[0.62, 0.72, 0.9], strength=1.0)
    cmd("add_light", type="sun", name="sun", rotation=[52.0, 0.0, 35.0], energy=4.0)


def ground_spread(path):
    image = bpy.data.images.load(path)
    width, height = image.size
    pixels = numpy.array(image.pixels[:]).reshape(height, width, 4)[: height // 2, :, :3]
    bpy.data.images.remove(image)
    luminance = pixels @ numpy.array([0.2126, 0.7152, 0.0722])
    return {"mean": round(float(luminance.mean()), 6), "std": round(float(luminance.std()), 6), "green": round(float((pixels[:, :, 1] - pixels[:, :, 0]).mean()), 6)}


def shots(stage):
    stats = {}
    for camera in ("eye", "wide"):
        result = cmd("render_preview", camera=camera, shading="shaded", resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        path = os.path.join(OUT, f"{camera}-{stage}.png")
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))
        stats[camera] = ground_spread(path)
    return stats


def main():
    cmd("new_scene")
    terrain()
    tree()
    rocks()
    cameras()
    before = shots("before")
    stones = [entry["name"] for entry in cmd("scene_info", names="rocks_*", limit=100)["objects"]]
    cmd("ground_cover", target="ground", preset="meadow", camera="eye", near=10.0, budget=BUDGET, obstacles=["oak_bark", *stones], trees=["oak_bark"], seed=5, wind=True)
    after = shots("after")
    cmd("ground_cover_export", path="meadow-cover.glb", name="GroundCover", mode="instances")
    cmd("save_blend", path="meadow-cover.blend")
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"commands": LOG, "before": before, "after": after}, handle, indent=2)


main()
