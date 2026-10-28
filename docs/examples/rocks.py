import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "rocks"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
BAKE_SIZE = int(os.environ.get("BLENDWORKS_BAKE_SIZE", "512"))
FRAGMENTS = int(os.environ.get("BLENDWORKS_FRAGMENTS", "11"))
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

BOULDER = {"size": [2.2, 1.5, 1.3], "at": [-2.4, 0.0], "spread": 0.3}
STONES = (
    {"name": "stone_a", "at": [1.8, -1.6], "size": [1.9, 1.4, 1.1], "seed": 7, "chips": 6, "wear": 1.0},
    {"name": "stone_b", "at": [3.4, 0.7], "size": [1.3, 1.0, 0.85], "seed": 9, "chips": 5, "wear": 0.9},
    {"name": "stone_c", "at": [1.2, 1.9], "size": [1.1, 0.85, 0.7], "seed": 17, "chips": 6, "wear": 0.8},
)
CHIPPED = {"name": "chipped_block", "at": [-0.6, -2.7], "size": [1.2, 0.9, 0.7], "seed": 21}


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "name": args.get("name"), "seconds": round(time.perf_counter() - started, 3), "mesh": result.get("mesh")})
    return result


def block(name, size, at, round_body=False):
    if round_body:
        cmd("add_primitive", type="ico_sphere", name=name, radius=0.5, subdivisions=4 if size[0] < 2.0 else 3, location=[at[0], at[1], size[2] / 2])
    else:
        cmd("add_primitive", type="cube", name=name, size=1.0, location=[at[0], at[1], size[2] / 2])
    cmd("transform", name=name, scale=size)
    cmd("apply_transform", name=name, scale=True)
    cmd("assign_material", name=name, material="granite")


def materials():
    cmd("material_procedural", name="ground", stone={"color": [0.3, 0.27, 0.22], "secondary_color": [0.15, 0.15, 0.11], "cracks": False, "cell_scale": 1.5})
    cmd("material_procedural", name="granite", stone={"color": [0.42, 0.4, 0.37], "cracks": False})
    cmd("material_procedural", name="fresh_rock", stone={"color": [0.68, 0.65, 0.6], "secondary_color": [0.52, 0.5, 0.46], "cracks": False})


def ground():
    cmd("add_primitive", type="plane", name="ground", size=16.0, location=[0.5, 0.0, 0.0])
    cmd("assign_material", name="ground", material="ground")


def boulder():
    block("boulder", BOULDER["size"], BOULDER["at"])
    cmd("chip", name="boulder", count=14, depth=0.5, seed=3, fresh_material="fresh_rock")
    result = cmd("fracture", name="boulder", pieces=FRAGMENTS, mode="binary", seed=5, min_size=0.15, fresh_material="fresh_rock")
    middle = [BOULDER["at"][0], BOULDER["at"][1], BOULDER["size"][2] / 2]
    for number, (piece, centre) in enumerate(zip(result["pieces"], result["centres"])):
        push = [(centre[axis] - middle[axis]) * BOULDER["spread"] for axis in range(3)]
        tumble = [(number * 37) % 31 - 15, (number * 53) % 29 - 14, (number * 71) % 41 - 20]
        cmd("transform", name=piece, location=[centre[0] + push[0], centre[1] + push[1], centre[2] + push[2] + 0.05], rotation=tumble)
    return result["pieces"]


def chipped_block():
    spec = CHIPPED
    block(spec["name"], spec["size"], spec["at"])
    cmd("chip", name=spec["name"], count=10, depth=0.3, seed=spec["seed"], fresh_material="fresh_rock")
    cmd("transform", name=spec["name"], rotation=[0, 0, 25])


def worn_stone(spec):
    name = spec["name"]
    block(name, spec["size"], spec["at"], round_body=True)
    result = cmd("fracture", name=name, pieces=2, mode="binary", seed=spec["seed"], min_size=0.4 * min(spec["size"]), fresh_material="fresh_rock")
    keep = max(zip(result["pieces"], result["volumes"]), key=lambda entry: entry[1])[0]
    cmd("delete", names=[piece for piece in result["pieces"] if piece != keep])
    cmd("rename", name=keep, new_name=name)
    cmd("chip", name=name, count=spec["chips"], depth=0.3 * max(spec["size"]), seed=spec["seed"], fresh_material="fresh_rock")
    cmd("abrade", name=name, amount=spec["wear"], seed=spec["seed"])
    reach = max(spec["size"])
    cmd("noise_displace", name=name, amplitude=0.18 * reach, seed=spec["seed"], scale=0.5 * reach, octaves=2, hurst=0.7, direction="z")
    cmd("noise_displace", name=name, amplitude=0.02 * reach, seed=spec["seed"] + 1, basis="worley_f2_minus_f1", mode="ridged", ridge_offset=0.5, scale=0.3 * reach, octaves=2, hurst=0.5)
    cmd("noise_displace", name=name, amplitude=0.03 * reach, seed=spec["seed"] + 2, scale=0.13 * reach, octaves=3, hurst=0.5)
    cmd("shade_smooth", name=name)
    cmd("set_origin", name=name, to="bottom_centre")
    cmd("transform", name=name, location=[spec["at"][0], spec["at"][1], 0.0])
    cmd("assign_material", name=name, material="granite")
    cmd("uv_smart_project", name=name, island_margin=0.01)
    cmd("bake", names=[name], channels=["base_color"], size=BAKE_SIZE, rewire=True, device="cpu", prefix=name)
    cmd("export", path=f"{name}.glb", names=[name])


def write_spec():
    spec = {"name": "worn stone", "format": "glb", "manifold": True, "natural": {"class": "rock", "solidity": {}, "surfaceRoughness": {}, "albedoVariation": {}}}
    with open(os.path.join(OUT, "rock.spec.json"), "w", encoding="utf-8") as handle:
        json.dump(spec, handle, indent=1)


def shot(name, point, width, direction, shading="shaded"):
    result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading=shading, resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
    with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
        handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    materials()
    ground()
    boulder()
    chipped_block()
    for spec in STONES:
        worn_stone(spec)
    write_spec()
    cmd("save_blend", path="rocks.blend")
    shot("overview", [0.2, -0.2, 0.4], 9.0, [0.5, -1.0, 0.6])
    shot("boulder", [-2.4, 0.0, 0.7], 4.2, [0.4, -1.0, 0.5])
    shot("stones", [1.9, 0.2, 0.3], 4.2, [0.3, -1.0, 0.55])
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)


main()
