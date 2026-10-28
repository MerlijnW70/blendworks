import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "eroded-terrain"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

TILE = 100.0
RESOLUTION = int(os.environ.get("BLENDWORKS_TERRAIN_RESOLUTION", "101"))
DROPLETS = int(os.environ.get("BLENDWORKS_DROPLETS", "300000"))
SWEEPS = int(os.environ.get("BLENDWORKS_SWEEPS", "160"))
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
TERRAIN = {
    "seed": 11,
    "basis": "perlin",
    "mode": "fbm",
    "scale": 140.0,
    "octaves": 5,
    "hurst": 0.9,
    "warp": 30.0,
    "warp_octaves": 2,
    "height": 35.0,
    "base_height": 40.0,
}


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3), "mesh": result.get("mesh"), "height_range": result.get("height_range")})
    return result


ERODE = {"mode": "both", "droplets": DROPLETS, "iterations": SWEEPS, "talus_angle": 40.0, "seed": 3, "capacity": 3.0, "erode_rate": 0.02, "deposit_rate": 0.1, "inertia": 0.1, "evaporation": 0.015, "max_lifetime": 200, "radius": 1.5}
TILES = [f"tile_{i}_{j}" for i in range(2) for j in range(2)]
ATTRIBUTE_MIXES = (
    ("Rock", "slope", 32.0, 44.0, [0.34, 0.31, 0.28]),
    ("Scoured", "erosion", 4.0, 6.5, [0.46, 0.41, 0.34]),
    ("Silt", "deposition", 0.03, 0.4, [0.5, 0.42, 0.28]),
)


def node(name, kind, inputs=None, settings=None):
    spec = {"name": name, "type": kind}
    if inputs:
        spec["inputs"] = [{"socket": socket, **value} for socket, value in inputs.items()]
    if settings:
        spec["settings"] = [{"name": key, **value} for key, value in settings.items()]
    return spec


def link(source, source_socket, target, target_socket):
    return {"from_node": source, "from_socket": source_socket, "to_node": target, "to_socket": target_socket}


def ground_material():
    nodes = [node("Soil", "rgb", {"Color": {"color": [0.1, 0.13, 0.05]}})]
    links = []
    previous = ("Soil", "Color")
    for label, attribute, low, high, colour in ATTRIBUTE_MIXES:
        nodes += [
            node(f"{label}Attribute", "attribute", settings={"attribute_type": {"text": "GEOMETRY"}, "attribute_name": {"text": attribute}}),
            node(f"{label}Mask", "map_range", {"From Min": {"number": low}, "From Max": {"number": high}}, {"clamp": {"boolean": True}}),
            node(f"{label}Colour", "rgb", {"Color": {"color": colour}}),
            node(f"{label}Mix", "mix", settings={"data_type": {"text": "RGBA"}}),
        ]
        links += [
            link(f"{label}Attribute", "Fac", f"{label}Mask", "Value"),
            link(f"{label}Mask", "Result", f"{label}Mix", "Factor"),
            link(previous[0], previous[1], f"{label}Mix", "A"),
            link(f"{label}Colour", "Color", f"{label}Mix", "B"),
        ]
        previous = (f"{label}Mix", "Result")
    nodes += [node("Ground", "principled_bsdf", {"Roughness": {"number": 0.92}}), node("Output", "material_output")]
    links += [link(previous[0], previous[1], "Ground", "Base Color"), link("Ground", "BSDF", "Output", "Surface")]
    cmd("material_nodes", name="ground", nodes=nodes, links=links)


def terrain():
    for i in range(2):
        for j in range(2):
            cmd("heightfield", name=f"tile_{i}_{j}", size=[TILE, TILE], resolution=RESOLUTION, tile=[i, j], attributes=["slope", "height"], **TERRAIN)
    return cmd("erode", name=TILES[0], names=TILES[1:], **ERODE)


def dress():
    ground_material()
    cmd("join", names=TILES, target=TILES[0])
    cmd("merge_by_distance", name=TILES[0], distance=0.001)
    cmd("shade_smooth", name=TILES[0])
    cmd("assign_material", name=TILES[0], material="ground")


CAMERAS = {
    "overview": ([300.0, -110.0, 200.0], [100.0, 100.0, 35.0], 35.0),
    "channels": ([110.0, -20.0, 110.0], [70.0, 80.0, 38.0], 40.0),
    "tile-joint": ([100.0, 20.0, 100.0], [100.0, 100.0, 38.0], 50.0),
}


def shots():
    cmd("add_light", type="sun", name="sun", rotation=[65.0, 0.0, -45.0], energy=4.0)
    cmd("set_world", color=[0.35, 0.45, 0.6], strength=0.7)
    for name, (location, target, lens) in CAMERAS.items():
        cmd("add_camera", name=f"camera_{name}", location=location, target=target, lens=lens)
    views = (("overview", "shaded"), ("overview", "clay"), ("channels", "shaded"), ("channels", "clay"), ("tile-joint", "clay"))
    for name, shading in views:
        result = cmd("render_preview", camera=f"camera_{name}", shading=shading, resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        suffix = "-clay" if shading == "clay" else ""
        with open(os.path.join(OUT, f"{name}{suffix}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    report = terrain()
    dress()
    cmd("save_blend", path="eroded-terrain.blend")
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"erosion": report, "commands": LOG}, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
