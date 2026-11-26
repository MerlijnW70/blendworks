import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "liquid-still-life"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "1000"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "512"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
SEGMENTS = int(os.environ.get("BLENDWORKS_LATHE_SEGMENTS", "96"))
RECEDING_ANGLE = 35.0
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


def rim(x, z, wall, steps=6):
    """A rounded lip from the outer to the inner wall at height z, a half circle of the wall's thickness."""
    radius = wall / 2.0
    return [[x - radius + radius * math.cos(math.pi * k / steps), z + radius * math.sin(math.pi * k / steps)] for k in range(steps + 1)]


def tumbler(top, bottom, height, wall, base):
    outer = [[0.0, 0.0], [bottom - 0.002, 0.0], [bottom, 0.0015], [top, height]]
    inner = [[top - wall, height], [bottom - wall * 1.4, base + 0.002], [bottom - wall * 1.4 - 0.003, base], [0.0, base]]
    return outer + rim(top, height, wall)[1:-1] + inner


def bowl_radius(share, widest):
    return widest * math.sin(math.pi * 0.5 * min(1.0, share * 1.35)) ** 0.7 * (1.0 - 0.22 * share * share)


def wine_glass():
    foot, stem, widest, wall = 0.036, 0.0035, 0.044, 0.0016
    start, depth = 0.09, 0.115
    outer = [[0.0, 0.0], [foot, 0.0], [foot, 0.0025], [0.01, 0.006], [stem, 0.012], [stem, start - 0.004]]
    shares = [k / 20 for k in range(21)]
    bowl = [[max(bowl_radius(share, widest), stem + 0.002), start + depth * share] for share in shares]
    top = bowl[-1][0]
    inner = [[bowl_radius(share, widest) - wall, start + depth * share] for share in reversed(shares[2:-1])]
    inner = [point for point in inner if point[0] > 0.004]
    return outer + bowl + rim(top, start + depth, wall)[1:-1] + [[top - wall, start + depth]] + inner + [[0.0, start + 0.008]]


def jar():
    radius, height, wall = 0.045, 0.11, 0.0035
    outer = [[0.0, 0.0], [radius - 0.006, 0.0], [radius, 0.006], [radius, height - 0.018], [radius - 0.006, height - 0.01], [radius - 0.006, height]]
    inner = [[radius - 0.006 - wall, height], [radius - 0.006 - wall, height - 0.012], [radius - wall, height - 0.02], [radius - wall, 0.01], [radius - wall - 0.005, 0.006], [0.0, 0.006]]
    return outer + rim(radius - 0.006, height, wall)[1:-1] + inner


def vessel(name, profile, location):
    cmd("lathe", name=name, profile=profile, segments=SEGMENTS)
    cmd("transform", name=name, location=location)


def table():
    cmd("add_primitive", type="cube", name="table", size=1.0, location=[0.0, 0.1, -0.025])
    cmd("transform", name="table", scale=[1.6, 0.9, 0.05])
    cmd("apply_transform", name="table", scale=True)
    cmd("bevel", name="table", width=0.004, segments=3, angle=30.0)
    cmd("uv_smart_project", name="table")
    cmd("material_procedural", name="oak_table", wood={"light_color": [0.3, 0.17, 0.08], "dark_color": [0.13, 0.065, 0.03], "ring_density": 140.0, "ring_distortion": 12.0, "roughness": 0.45})
    cmd("assign_material", name="table", material="oak_table")
    cmd("add_primitive", type="plane", name="wall", size=6.0, location=[0.0, 2.2, 1.5], rotation=[90.0, 0.0, 0.0])
    cmd("material_procedural", name="plaster", concrete={"color": [0.16, 0.15, 0.14], "variation": 0.25, "pores": 0.2})
    cmd("assign_material", name="wall", material="plaster")


def liquids():
    vessel("glass_water", tumbler(0.034, 0.029, 0.1, 0.0022, 0.012), [-0.29, 0.02, 0.0])
    cmd("liquid_fill", container="glass_water", preset="water_fresh", fill=0.72, name="water", glass=True)
    vessel("glass_wine", wine_glass(), [-0.12, 0.12, 0.0])
    cmd("liquid_fill", container="glass_wine", preset="wine", volume=0.12, name="wine", glass=True)
    vessel("glass_milk", tumbler(0.033, 0.03, 0.12, 0.0024, 0.01), [0.05, 0.0, 0.0])
    cmd("liquid_fill", container="glass_milk", preset="milk", fill=0.8, name="milk", glass=True)
    vessel("glass_oil", tumbler(0.026, 0.026, 0.075, 0.0025, 0.012), [0.19, 0.14, 0.0])
    cmd("liquid_fill", container="glass_oil", preset="oil", fill=0.62, name="oil", glass=True)
    vessel("jar", jar(), [0.3, 0.1, 0.0])
    cmd("liquid_fill", container="jar", preset="honey", fill=0.82, name="honey", glass=True, voxels=72)
    cmd("liquid_fill", preset="coffee", name="coffee", spill={"point": [-0.05, -0.18, 0.0], "area": 0.018, "surface": "table", "contact_angle": RECEDING_ANGLE}, seed=4)


def lights():
    cmd("set_world", color=[0.02, 0.022, 0.025], strength=1.0)
    cmd("add_light", type="area", name="window", location=[-0.9, 0.75, 0.55], rotation=[-60.0, 0.0, -130.0], energy=220.0, size=0.9, color=[1.0, 0.96, 0.9])
    cmd("add_light", type="area", name="fill", location=[0.9, -1.2, 0.6], rotation=[60.0, 0.0, 35.0], energy=18.0, size=1.5, color=[0.9, 0.95, 1.0])
    cmd("add_light", type="area", name="top", location=[0.1, 0.3, 1.6], rotation=[0.0, 0.0, 0.0], energy=60.0, size=1.6, color=[1.0, 0.98, 0.95])
    cmd("add_camera", name="eye", location=[0.03, -1.05, 0.26], target=[0.02, 0.05, 0.045], lens=50.0)
    cmd("camera_setup", name="eye", fstop=4.0, focus_object="glass_wine", exposure=0.0, view_transform="AgX", look="base_contrast")


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    cmd("new_scene")
    table()
    liquids()
    lights()
    cmd("save_blend", path="liquid-still-life.blend")
    final = cmd("render_final", path="still-life.png", camera="eye", width=WIDTH, height=HEIGHT, samples=SAMPLES, time_limit=SECONDS, device=DEVICE, preview=False)
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"render": {key: final[key] for key in ("samples", "time_budget", "liquids", "device")}, "commands": LOG}, handle, indent=1)


if __name__ == "__main__":
    main()
