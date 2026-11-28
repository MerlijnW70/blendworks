import base64
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "phyllotaxis"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
SEEDS = 1100
SEED_C = 0.0042
CONE_SCALES = 89
ROSETTE_LEAVES = 89


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    LOG.append({"cmd": name, "seconds": round(time.perf_counter() - started, 3), "count": result.get("count"), "phyllotaxis": result.get("phyllotaxis"), "mesh": result.get("mesh")})
    return result


def blade(name, length, width, thickness, width_profile, thickness_profile, bend, rows=14, across=6):
    vertices, faces, uvs, index = [], [], [], {}

    def vertex(point):
        key = tuple(round(value, 9) for value in point)
        if key not in index:
            index[key] = len(vertices)
            vertices.append(list(key))
        return index[key]

    def surface(side):
        grid = []
        for row in range(rows + 1):
            t = row / rows
            span = width * width_profile(t)
            line = []
            for column in range(across + 1):
                s = column / across
                lateral = 2.0 * s - 1.0
                height = bend * length * t * t + side * 0.5 * thickness * thickness_profile(t) * (1.0 - lateral * lateral) ** 0.5 - 0.12 * span * lateral * lateral
                line.append(vertex((length * t, (s - 0.5) * span, height)))
            grid.append(line)
        for row in range(rows):
            for column in range(across):
                corners = [(row, column), (row + 1, column), (row + 1, column + 1), (row, column + 1)]
                ring = [grid[r][c] for r, c in corners]
                texture = [(c / across, r / rows) for r, c in corners]
                if side < 0:
                    ring, texture = ring[::-1], texture[::-1]
                keep = [position for position, vertex_index in enumerate(ring) if vertex_index != ring[position - 1]]
                if len(keep) >= 3:
                    faces.append([ring[position] for position in keep])
                    uvs.extend(list(texture[position]) for position in keep)

    surface(1)
    surface(-1)
    cmd("mesh_from_data", name=name, vertices=vertices, faces=faces, uvs=uvs, smooth=True)


def petal_width(t):
    return max(0.04, math.sin(math.pi * t ** 0.8) ** 0.75)


def scale_width(t):
    return max(0.03, (0.55 + 0.45 * min(1.0, 4.0 * t)) * (1.0 - t ** 5) ** 0.5)


def leaf_width(t):
    return max(0.03, (t ** 0.4) * (1.0 - t ** 3) ** 0.5 * 1.45)


def materials():
    cmd("material_procedural", name="soil", soil={"scale": 0.2, "moisture": 0.5})
    cmd("material_procedural", name="petal", leaf={"leaf_type": "petal", "color": [0.95, 0.5, 0.0], "dark_color": [0.6, 0.2, 0.0], "vein_color": [1.0, 0.68, 0.04], "vein_pairs": 7})
    cmd("material_procedural", name="seed", dirt={"color": [0.045, 0.024, 0.012]})
    cmd("material_procedural", name="sepal", leaf={"color": [0.05, 0.17, 0.02]})
    cmd("material_procedural", name="cone_scale", bark={"color": [0.22, 0.12, 0.055], "fissure_color": [0.05, 0.025, 0.012], "lichen_color": [0.3, 0.18, 0.09], "fissure_spacing": 0.007, "fissure_depth": 0.5})
    cmd("material_procedural", name="cone_core", bark={"color": [0.06, 0.035, 0.018], "fissure_spacing": 0.007})
    cmd("material_procedural", name="succulent", leaf={"color": [0.2, 0.34, 0.2], "dark_color": [0.12, 0.2, 0.14], "vein_color": [0.42, 0.52, 0.34], "vein_pairs": 4})


def ground():
    cmd("add_primitive", type="plane", name="ground", size=1.0, location=[0.5, 0.0, 0.0])
    cmd("transform", name="ground", scale=[30.0, 20.0, 1.0])
    cmd("assign_material", name="ground", material="soil")


def sunflower():
    cmd("add_primitive", type="sphere", name="seed_mesh", radius=0.0034, segments=12, rings=8)
    cmd("transform", name="seed_mesh", scale=[1.3, 0.8, 0.55])
    cmd("apply_transform", name="seed_mesh", scale=True)
    cmd("shade_smooth", name="seed_mesh")
    cmd("assign_material", name="seed_mesh", material="seed")
    cmd("instances", source="seed_mesh", name="seeds", phyllotaxis={"count": SEEDS, "c": SEED_C, "golden": True, "scale_by_age": {"from": 0.55, "to": 1.0, "curve": "ease_out"}, "tilt_by_age": {"from": 0.0, "to": 12.0}})
    cmd("delete", names=["seed_mesh"])
    blade("petal_mesh", 0.07, 0.03, 0.0015, petal_width, lambda t: 1.0 - t ** 3, 0.14)
    cmd("assign_material", name="petal_mesh", material="petal")
    rim = SEEDS
    cmd("instances", source="petal_mesh", name="petals_inner", phyllotaxis={"count": 34, "c": SEED_C, "golden": True, "start": rim, "tilt_by_age": {"from": 14.0, "to": 24.0}, "scale_by_age": {"from": 0.9, "to": 1.05}, "jitter": {"amount": 0.05, "rotation": 5.0, "scale": 0.06, "seed": 3}})
    cmd("instances", source="petal_mesh", name="petals_outer", phyllotaxis={"count": 55, "c": SEED_C, "golden": True, "start": rim + 400, "tilt_by_age": {"from": 30.0, "to": 46.0}, "scale_by_age": {"from": 1.05, "to": 1.25}, "jitter": {"amount": 0.05, "rotation": 6.0, "scale": 0.06, "seed": 4}})
    cmd("delete", names=["petal_mesh"])
    cmd("add_primitive", type="cylinder", name="receptacle", radius=SEED_C * math.sqrt(SEEDS) * 1.02, depth=0.03, segments=64)
    cmd("assign_material", name="receptacle", material="cone_core")
    cmd("transform", name="receptacle", location=[0.0, 0.0, -0.017])
    for name in ("seeds", "petals_inner", "petals_outer", "receptacle"):
        cmd("transform", name=name, location=[0.0, 0.0, 0.06], relative=True)


def pine_cone():
    radius, height = 0.036, 0.1
    blade("scale_mesh", 0.042, 0.03, 0.006, scale_width, lambda t: 0.35 + 0.65 * t, 0.05)
    cmd("assign_material", name="scale_mesh", material="cone_scale")
    cmd("instances", source="scale_mesh", name="cone_scales", phyllotaxis={"count": CONE_SCALES, "mode": "cone", "radius": radius, "height": height, "golden": True, "scale_by_age": {"from": 0.4, "to": 1.0, "curve": "ease_out"}, "tilt_by_age": {"from": 6.0, "to": 40.0, "curve": "ease_in"}})
    cmd("delete", names=["scale_mesh"])
    cmd("add_primitive", type="cone", name="cone_core", radius=radius * 0.93, top_radius=0.0, depth=height, segments=40, location=[0.0, 0.0, height * 0.5])
    cmd("assign_material", name="cone_core", material="cone_core")
    for name in ("cone_scales", "cone_core"):
        cmd("transform", name=name, location=[0.5, 0.0, 0.0], relative=True)


def rosette():
    radius = 0.03
    blade("leaf_mesh", 0.052, 0.03, 0.007, leaf_width, lambda t: 1.0 - 0.45 * t, 0.12)
    cmd("assign_material", name="leaf_mesh", material="succulent")
    cmd("instances", source="leaf_mesh", name="rosette", phyllotaxis={"count": ROSETTE_LEAVES, "mode": "sphere", "radius": radius, "polar_extent": 112.0, "golden": True, "scale_by_age": {"from": 0.3, "to": 1.0, "curve": "ease_out"}, "tilt_by_age": {"from": 82.0, "to": 18.0, "curve": "ease_out"}})
    cmd("delete", names=["leaf_mesh"])
    cmd("add_primitive", type="sphere", name="rosette_heart", radius=radius * 0.9, segments=24, rings=12)
    cmd("assign_material", name="rosette_heart", material="succulent")
    for name in ("rosette", "rosette_heart"):
        cmd("transform", name=name, location=[1.0, 0.0, 0.055], relative=True)


def shots():
    views = {
        "sunflower": ([0.0, 0.0, 0.07], 0.42, [0.0, -0.45, 1.0], "shaded"),
        "sunflower-seeds": ([0.0, 0.0, 0.07], 0.2, [0.0, -0.001, 1.0], "shaded"),
        "pine-cone": ([0.5, 0.0, 0.055], 0.2, [0.0, -1.0, 0.45], "shaded"),
        "pine-cone-top": ([0.5, 0.0, 0.055], 0.2, [0.0, -0.001, 1.0], "shaded"),
        "rosette": ([1.0, 0.0, 0.06], 0.2, [0.0, -0.55, 1.0], "shaded"),
        "rosette-top": ([1.0, 0.0, 0.06], 0.2, [0.0, -0.001, 1.0], "shaded"),
        "overview": ([0.5, 0.0, 0.05], 1.7, [0.0, -1.0, 0.7], "shaded"),
    }
    for name, (point, width, direction, shading) in views.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading=shading, resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    materials()
    ground()
    sunflower()
    pine_cone()
    rosette()
    cmd("save_blend", path="phyllotaxis.blend")
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
