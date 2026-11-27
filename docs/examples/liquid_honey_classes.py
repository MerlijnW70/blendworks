import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler, liquid_presets

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "liquid-honey"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
WIDTH = int(os.environ.get("BLENDWORKS_SHOT_WIDTH", "1600"))
HEIGHT = int(os.environ.get("BLENDWORKS_SHOT_HEIGHT", "700"))
SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "384"))
SECONDS = float(os.environ.get("BLENDWORKS_SHOT_SECONDS", "300"))
SEGMENTS = int(os.environ.get("BLENDWORKS_LATHE_SEGMENTS", "96"))
SPACING = 0.115
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
    radius = wall / 2.0
    return [[x - radius + radius * math.cos(math.pi * k / steps), z + radius * math.sin(math.pi * k / steps)] for k in range(steps + 1)]


def jar():
    radius, height, wall = 0.045, 0.11, 0.0035
    outer = [[0.0, 0.0], [radius - 0.006, 0.0], [radius, 0.006], [radius, height - 0.018], [radius - 0.006, height - 0.01], [radius - 0.006, height]]
    inner = [[radius - 0.006 - wall, height], [radius - 0.006 - wall, height - 0.012], [radius - wall, height - 0.02], [radius - wall, 0.01], [radius - wall - 0.005, 0.006], [0.0, 0.006]]
    return outer + rim(radius - 0.006, height, wall)[1:-1] + inner


def classes():
    """The USDA colour classes of honey in the order of their scale, water white to dark amber."""
    return list(liquid_presets.HONEY_CLASSES)


def scene():
    cmd("add_primitive", type="cube", name="table", size=1.0, location=[0.0, 0.1, -0.025])
    cmd("transform", name="table", scale=[1.8, 0.8, 0.05])
    cmd("apply_transform", name="table", scale=True)
    cmd("uv_smart_project", name="table")
    cmd("material_procedural", name="oak_table", wood={"light_color": [0.3, 0.17, 0.08], "dark_color": [0.13, 0.065, 0.03], "ring_density": 140.0, "ring_distortion": 12.0, "roughness": 0.45})
    cmd("assign_material", name="table", material="oak_table")
    cmd("add_primitive", type="plane", name="wall", size=6.0, location=[0.0, 0.7, 1.5], rotation=[90.0, 0.0, 0.0])
    cmd("material_procedural", name="plaster", concrete={"color": [0.45, 0.43, 0.4], "variation": 0.25, "pores": 0.2})
    cmd("assign_material", name="wall", material="plaster")
    names = classes()
    for index, name in enumerate(names):
        x = (index - (len(names) - 1) / 2.0) * SPACING
        cmd("lathe", name=f"jar_{name}", profile=jar(), segments=SEGMENTS)
        cmd("transform", name=f"jar_{name}", location=[x, 0.0, 0.0])
        cmd("liquid_fill", container=f"jar_{name}", preset=f"honey_{name}", fill=0.82, name=f"honey_{name}", glass=True, voxels=64)


def lights():
    cmd("set_world", color=[0.03, 0.03, 0.035], strength=1.0)
    cmd("add_light", type="area", name="back", location=[0.0, 0.62, 0.16], rotation=[90.0, 0.0, 0.0], energy=140.0, size=1.1, color=[1.0, 0.97, 0.92])
    cmd("add_light", type="area", name="fill", location=[0.4, -1.2, 0.7], rotation=[60.0, 0.0, 15.0], energy=25.0, size=1.5, color=[0.95, 0.97, 1.0])
    cmd("add_camera", name="eye", location=[0.0, -1.35, 0.2], target=[0.0, 0.0, 0.06], lens=50.0)
    cmd("camera_setup", name="eye", fstop=8.0, focus_object=f"jar_{classes()[3]}", exposure=0.0, view_transform="AgX", look="base_contrast")


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    cmd("new_scene")
    scene()
    lights()
    cmd("save_blend", path="liquid-honey.blend")
    final = cmd("render_final", path="honey.png", camera="eye", width=WIDTH, height=HEIGHT, samples=SAMPLES, time_limit=SECONDS, device=DEVICE, preview=False)
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"classes": classes(), "render": {key: final[key] for key in ("samples", "time_budget", "liquids", "device")}, "commands": LOG}, handle, indent=1)


if __name__ == "__main__":
    main()
