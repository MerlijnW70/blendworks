import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "noise-terrain"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

TILE = 100.0
RESOLUTION = int(os.environ.get("BLENDWORKS_TERRAIN_RESOLUTION", "101"))
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
TERRAIN = {
    "seed": 11,
    "basis": "perlin",
    "mode": "ridged",
    "ridge_offset": 1.0,
    "scale": 150.0,
    "octaves": 7,
    "hurst": 0.7,
    "warp": 45.0,
    "warp_octaves": 2,
    "height": 110.0,
    "base_height": 0.0,
}


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3), "mesh": result.get("mesh"), "height_range": result.get("height_range")})
    return result


def terrain():
    for i in range(2):
        for j in range(2):
            cmd("heightfield", name=f"tile_{i}_{j}", size=[TILE, TILE], resolution=RESOLUTION, tile=[i, j], skirt=True, skirt_depth=14.0, attributes=["slope", "height"], **TERRAIN)
            cmd("assign_material", name=f"tile_{i}_{j}", material="ground")


def rock():
    cmd("add_primitive", type="ico_sphere", name="rock", radius=1.6, subdivisions=6, location=[-9.0, 50.0, 40.0])
    cmd("transform", name="rock", scale=[1.35, 1.0, 0.8])
    cmd("apply_transform", name="rock", scale=True)
    cmd("noise_displace", name="rock", amplitude=0.45, seed=3, mode="billow", scale=2.6, octaves=3, hurst=0.9)
    cmd("noise_displace", name="rock", amplitude=0.2, seed=5, basis="worley_f2_minus_f1", mode="ridged", ridge_offset=0.7, scale=1.1, octaves=3, hurst=0.6, warp=0.2, warp_octaves=2)
    cmd("noise_displace", name="rock", amplitude=0.03, seed=8, scale=0.3, octaves=3, hurst=0.5)
    cmd("shade_smooth", name="rock")
    cmd("assign_material", name="rock", material="boulder")


def materials():
    cmd("material_procedural", name="ground", stone={"color": [0.28, 0.24, 0.19], "secondary_color": [0.14, 0.15, 0.1], "cracks": False})
    cmd("material_procedural", name="boulder", stone={"color": [0.4, 0.38, 0.35], "cracks": False})


def shots():
    views = {
        "overview": ([100.0, 100.0, 50.0], 330.0, [0.9, -1.0, 0.45], "shaded"),
        "ridge-detail": ([60.0, 40.0, 60.0], 110.0, [0.3, -0.8, 1.0], "clay"),
        "overview-clay": ([100.0, 100.0, 50.0], 330.0, [0.9, -1.0, 0.45], "clay"),
        "tile-joint": ([100.0, 100.0, 60.0], 90.0, [0.25, -0.6, 1.0], "clay"),
        "rock": ([-9.0, 50.0, 40.0], 5.0, [0.4, -1.0, 0.4], "shaded"),
    }
    for name, (point, width, direction, shading) in views.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading=shading, resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    materials()
    terrain()
    rock()
    cmd("save_blend", path="noise-terrain.blend")
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
