"""Rocks that read as stone: a granite boulder seen from one metre, a sandstone ledge and a river cobble bed, each built with
commands only and rendered with render_final at its default settings (1920 x 1080, adaptive sampling, denoising).

Run: blender --background --factory-startup --python docs/examples/rock_realism.py -- <out dir>
BLENDWORKS_SCENES picks scenes (boulder,ledge,cobbles); BLENDWORKS_SHOT_WIDTH, _HEIGHT and _SAMPLES shrink a preview."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "rock-realism"))
SCENES = os.environ.get("BLENDWORKS_SCENES", "boulder,ledge,cobbles").split(",")
SHOT = {key: int(os.environ[f"BLENDWORKS_SHOT_{key.upper()}"]) for key in ("width", "height", "samples") if f"BLENDWORKS_SHOT_{key.upper()}" in os.environ}
DEVICE = os.environ.get("BLENDWORKS_DEVICE")
HANDLER = None
LOG = []


def cmd(name, /, **args):
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    LOG.append(name)
    return reply["result"]


def stage(ground, sun):
    cmd("new_scene")
    cmd("add_primitive", type="plane", name="ground", size=400.0)
    cmd("subdivide", name="ground", cuts=10)
    cmd("noise_displace", name="ground", amplitude=0.05, scale=2.0, octaves=4, hurst=0.6, seed=2, direction="z")
    cmd("material_procedural", name="ground", **ground)
    cmd("assign_material", name="ground", material="ground")
    cmd("sky", sun=sun)


def stone(name, size, at, material, seed, chips, depth, passes, yaw=0.0, base=None, cell=True):
    """A stone the way shore_stones makes one: the second largest Voronoi cell of a block (most of its faces are breaks, not
    the block's), stretched to its size, chipped with fresh faces, worn in passes of one per cent of its volume, with a little
    relief at its own scale; it stands at base metres or is sunk by 0.15 of its height, and is turned. Without cell it stays
    a block bounded by joints and bedding planes, as bedrock breaks."""
    cmd("add_primitive", type="cube", name=name, size=1.0)
    if cell:
        cells = cmd("fracture", name=name, pieces=8, mode="voronoi", seed=seed, min_size=0.05)
        ranked = sorted(zip(cells["volumes"], cells["pieces"]), reverse=True)
        cmd("delete", names=[piece for _, piece in ranked if piece != ranked[1][1]])
        cmd("rename", name=ranked[1][1], new_name=name)
    cmd("set_origin", name=name, to="geometry_centre")
    cell = cmd("scene_info", names=name)["objects"][0]["bounds"]["size"]
    cmd("transform", name=name, location=[0.0, 0.0, 0.0], scale=[want / have for want, have in zip(size, cell)])
    cmd("apply_transform", name=name, location=True, scale=True)
    cmd("assign_material", name=name, material=material)
    longest = max(size)
    cmd("chip", name=name, count=chips, depth=depth * longest, seed=seed + 1)
    cmd("abrade", name=name, amount=0.0, edge_length=longest / 14.0)
    for index in range(passes):
        cmd("abrade", name=name, amount=0.1, seed=seed + 10 + index, edge_length=longest / 14.0)
    cmd("noise_displace", name=name, amplitude=0.008 * longest, scale=0.25 * longest, octaves=5, hurst=0.5, seed=seed + 2)
    cmd("shade_smooth", name=name, angle=35.0)
    cmd("set_origin", name=name, to="bottom_centre")
    cmd("transform", name=name, location=[at[0], at[1], -0.15 * size[2] if base is None else base], rotation=[0.0, 0.0, yaw])


def render(name, camera, location, target, lens):
    cmd("add_camera", name=camera, location=location, target=target, lens=lens)
    cmd("camera_setup", name=camera, view_transform="AgX", look="base_contrast")
    arguments = dict(SHOT, path=f"{name}.png", camera=camera, preview=False)
    if DEVICE:
        arguments["device"] = DEVICE
    return cmd("render_final", **arguments)


def boulder():
    """A granite boulder in a meadow, its top lit and lichened, seen from about a metre."""
    stage({"grass_ground": {"density": 0.6, "dryness": 0.3}}, {"elevation": 32.0, "azimuth": 220.0})
    cmd("material_procedural", name="granite", stone={"lithology": "granite", "lichen": 0.35, "moss": 0.2})
    stone("boulder", [2.2, 1.6, 1.15], [0.0, 0.0], "granite", 7, 6, 0.1, 1, yaw=20.0)
    return render("boulder", "near", [0.55, -1.35, 1.05], [0.1, -0.2, 0.55], 35.0)


def ledge():
    """A ledge of sandstone beds: three slabs, the upper ones set back, broken at their ends, little worn."""
    stage({"soil": {}}, {"elevation": 24.0, "azimuth": 250.0})
    cmd("material_procedural", name="sandstone", stone={"lithology": "sandstone", "lichen": 0.2, "moss": 0.25})
    beds = (([3.4, 2.0, 0.6], [0.0, 0.0], 5.0), ([2.8, 1.6, 0.5], [0.25, 0.4], -4.0), ([2.0, 1.2, 0.45], [0.4, 0.7], 8.0))
    top = -0.1
    for index, (size, at, yaw) in enumerate(beds):
        stone(f"bed_{index}", size, at, "sandstone", 31 + 5 * index, 10, 0.12, 1, yaw=yaw, base=top, cell=False)
        top = cmd("scene_info", names=f"bed_{index}")["objects"][0]["bounds"]["max"][2] - 0.04
    return render("ledge", "side", [2.6, -3.2, 1.4], [0.2, 0.2, 0.55], 40.0)


def cobbles():
    """A dry bar of river cobbles: granite, basalt and sandstone, well rounded, in sizes of a few centimetres to thirty,
    scattered close and partly buried in the gravel."""
    stage({"soil": {}}, {"elevation": 40.0, "azimuth": 200.0})
    kinds = (("granite", "granite"), ("basalt", "basalt"), ("sandstone", "sandstone"))
    sources = []
    for index, (material, lithology) in enumerate(kinds):
        cmd("material_procedural", name=material, stone={"lithology": lithology, "lichen": 0.05, "moss": 0.0})
        for variant in range(2):
            name = f"cobble_{index}_{variant}"
            stone(name, [1.0, 0.7 + 0.1 * variant, 0.45 + 0.08 * index], [40.0 + 3.0 * len(sources), 40.0], material, 50 + 7 * len(sources), 3, 0.12, 12)
            sources.append({"name": name})
    cmd("add_primitive", type="plane", name="gravel", size=5.0, location=[0.0, 0.8, 0.02])
    cmd("subdivide", name="gravel", cuts=6)
    cmd("assign_material", name="gravel", material="ground")
    cmd("scatter", target="gravel", sources=sources, min_distance=0.1, scale_range=[0.07, 0.32], scale_distribution="lognormal",
        align="blend", align_factor=0.8, random_yaw=True, tilt=10.0, embed=0.25, seed=9, name="bar", realize=True)
    cmd("delete", names=[source["name"] for source in sources])
    return render("cobbles", "low", [0.0, -1.6, 0.9], [0.0, 0.3, 0.0], 35.0)


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    renders = {}
    for scene in SCENES:
        result = {"boulder": boulder, "ledge": ledge, "cobbles": cobbles}[scene]()
        renders[scene] = {key: result.get(key) for key in ("rock_detail", "samples", "time_budget", "device")}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump({"renders": renders, "commands": len(LOG)}, handle, indent=1, default=str)


if __name__ == "__main__":
    main()
