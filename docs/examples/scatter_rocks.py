import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "scatter-rocks"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

TILE = 100.0
RESOLUTION = int(os.environ.get("BLENDWORKS_TERRAIN_RESOLUTION", "161"))
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
ROCK_RADIUS = 1.0
SMALLEST_SCALE = 0.3
LARGEST_SCALE = 2.4
FOOTPRINT = 2.0 * ROCK_RADIUS
VARIANTS = 3


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3), "count": result.get("count"), "min_pair_distance": result.get("min_pair_distance"), "masked_out": result.get("masked_out"), "fitted_exponent": result.get("fitted_exponent")})
    return result


def materials():
    cmd("material_procedural", name="ground", stone={"color": [0.25, 0.21, 0.16], "secondary_color": [0.13, 0.12, 0.09], "cracks": False})
    cmd("material_procedural", name="boulder", stone={"color": [0.42, 0.4, 0.37], "secondary_color": [0.26, 0.25, 0.23], "cracks": False})


def terrain():
    cmd(
        "heightfield",
        name="ground",
        size=[TILE, TILE],
        resolution=RESOLUTION,
        height=24.0,
        seed=5,
        scale=60.0,
        octaves=6,
        hurst=0.8,
        warp=16.0,
        skirt=True,
        skirt_depth=8.0,
        attributes=["slope", "height"],
    )
    cmd("assign_material", name="ground", material="ground")


def rocks():
    for variant in range(VARIANTS):
        name = f"rock_{variant}"
        cmd("add_primitive", type="ico_sphere", name=name, radius=ROCK_RADIUS, subdivisions=5, location=[-200.0 - 10.0 * variant, 0.0, 0.0])
        cmd("transform", name=name, scale=[1.0 + 0.15 * variant, 1.0, 0.7 + 0.08 * variant])
        cmd("apply_transform", name=name, scale=True)
        cmd("noise_displace", name=name, amplitude=0.28, seed=3 + variant, mode="billow", scale=1.8, octaves=3, hurst=0.9)
        cmd("noise_displace", name=name, amplitude=0.12, seed=7 + variant, basis="worley_f2_minus_f1", mode="ridged", ridge_offset=0.7, scale=0.8, octaves=3, hurst=0.6)
        cmd("noise_displace", name=name, amplitude=0.02, seed=11 + variant, scale=0.25, octaves=3, hurst=0.5)
        cmd("shade_smooth", name=name)
        cmd("set_origin", name=name, to="bottom_centre")
        cmd("assign_material", name=name, material="boulder")


def scatter():
    cmd(
        "scatter",
        target="ground",
        sources=[{"name": f"rock_{variant}"} for variant in range(VARIANTS)],
        min_distance=FOOTPRINT * SMALLEST_SCALE,
        density_mask=["slope"],
        slope_range=[0.0, 38.0],
        scale_range=[SMALLEST_SCALE, LARGEST_SCALE],
        scale_distribution="power",
        scale_exponent=-2.0,
        align="blend",
        align_factor=0.6,
        random_yaw=True,
        tilt=6.0,
        embed=0.22,
        seed=21,
        name="rubble",
    )
    for variant in range(VARIANTS):
        cmd("delete", names=[f"rock_{variant}"])


def shots():
    views = {
        "overview": ([50.0, 50.0, 8.0], 70.0, [0.8, -1.0, 0.55], "shaded"),
        "slope": ([40.0, 44.0, 8.0], 30.0, [0.6, -1.0, 0.5], "shaded"),
        "closeup": ([56.0, 58.0, 8.0], 14.0, [0.5, -1.0, 0.45], "shaded"),
        "top": ([50.0, 50.0, 8.0], 70.0, [0.0, -0.001, 1.0], "clay"),
    }
    for name, (point, width, direction, shading) in views.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading=shading, resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    materials()
    terrain()
    rocks()
    scatter()
    cmd("save_blend", path="scatter-rocks.blend")
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
