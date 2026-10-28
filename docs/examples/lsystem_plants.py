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
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "lsystem-plants"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
os.makedirs(OUT, exist_ok=True)
HANDLER = Handler(OUT, allow_python=False, desktop=False)
LOG = []

SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "32"))
SUMMARY_KEYS = ("method", "nodes", "tips", "branchings", "max_order", "base_radius", "height", "spread", "exponent")
HERB_X, BUSH_X, TREE_X, FERN_X = -2.5, 0.0, 9.0, 3.5
BUSH_SEEDS = (4, 7, 12)
BUSH_GAP = 1.1


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    if name == "lsystem":
        entry.update({"name": result["name"], **{key: result.get(key) for key in SUMMARY_KEYS}, "lsystem": result["lsystem"]})
    if name == "export":
        entry["skeletons"] = result.get("skeletons", [])
    LOG.append(entry)
    return result


def blade(name, length, width, thickness, width_profile, bend, rows=12, across=4):
    vertices, faces, uvs, index = [], [], [], {}

    def vertex(point):
        key = tuple(round(value, 9) for value in point)
        if key not in index:
            index[key] = len(vertices)
            vertices.append(list(key))
        return index[key]

    for side in (1, -1):
        grid = []
        for row in range(rows + 1):
            t = row / rows
            span = width * width_profile(t)
            line = []
            for column in range(across + 1):
                s = column / across
                lateral = 2.0 * s - 1.0
                height = bend * length * t * t + side * 0.5 * thickness * (1.0 - lateral * lateral) ** 0.5 * (1.0 - t) - 0.18 * span * lateral * lateral
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
    cmd("mesh_from_data", name=name, vertices=vertices, faces=faces, uvs=uvs, smooth=True)


def leaf_profile(t):
    return max(0.05, math.sin(math.pi * t ** 0.7) ** 0.8)


def petal_profile(t):
    return max(0.08, math.sin(math.pi * t ** 0.9) ** 0.7)


def leaflet_profile(t):
    return max(0.1, math.sin(math.pi * t ** 0.6))


def materials():
    cmd("material_procedural", name="soil", soil={"scale": 0.3, "moisture": 0.45})
    cmd("material_procedural", name="stem", leaf={"color": [0.16, 0.3, 0.06], "dark_color": [0.08, 0.17, 0.03], "vein_color": [0.25, 0.4, 0.1], "vein_pairs": 2})
    cmd("material_procedural", name="bark", bark={"grain": "z"})
    cmd("material_procedural", name="leaf", leaf={"color": [0.1, 0.34, 0.06], "dark_color": [0.05, 0.2, 0.03], "vein_color": [0.3, 0.5, 0.14], "vein_pairs": 6})
    cmd("material_procedural", name="fern_leaf", leaf={"color": [0.14, 0.38, 0.08], "dark_color": [0.07, 0.22, 0.04], "vein_color": [0.35, 0.55, 0.18], "vein_pairs": 3})
    cmd("material_procedural", name="petal_yellow", leaf={"color": [0.95, 0.72, 0.05], "dark_color": [0.8, 0.45, 0.02], "vein_color": [1.0, 0.85, 0.2], "vein_pairs": 5, "translucency": 0.3})
    cmd("material_procedural", name="petal_pink", leaf={"color": [0.95, 0.35, 0.5], "dark_color": [0.75, 0.15, 0.3], "vein_color": [1.0, 0.6, 0.7], "vein_pairs": 5, "translucency": 0.3})
    cmd("material_procedural", name="heart", dirt={"color": [0.25, 0.12, 0.02]})


def flower(name, size, petal_material, count):
    blade("petal", size, size * 0.42, size * 0.04, petal_profile, 0.18)
    cmd("assign_material", name="petal", material=petal_material)
    cmd("instances", source="petal", name=f"{name}_petals", circle={"centre": [0.0, 0.0, 0.0], "radius": size * 0.12, "count": count}, align="radial", realize=True)
    cmd("delete", names=["petal"])
    cmd("add_primitive", type="sphere", name=f"{name}_heart", radius=size * 0.17, segments=14, rings=8, location=[0.0, 0.0, size * 0.03])
    cmd("assign_material", name=f"{name}_heart", material="heart")
    cmd("join", names=[f"{name}_petals", f"{name}_heart"], target=f"{name}_petals")
    cmd("rename", name=f"{name}_petals", new_name=name)
    cmd("transform", name=name, rotation=[0.0, 90.0, 0.0])
    cmd("apply_transform", name=name, rotation=True)
    cmd("transform", name=name, location=[0.0, 0.0, -20.0])


def leaf(name, length, material, profile=leaf_profile, bend=0.12):
    blade(name, length, length * 0.5, length * 0.03, profile, bend)
    cmd("assign_material", name=name, material=material)
    cmd("transform", name=name, location=[0.0, 0.0, -20.0])


def ground():
    cmd("add_primitive", type="plane", name="ground", size=1.0, location=[3.5, 0.0, 0.0])
    cmd("transform", name="ground", scale=[40.0, 24.0, 1.0])
    cmd("assign_material", name="ground", material="soil")


def herb():
    cmd(
        "lsystem",
        name="herb",
        preset="bush_1_25",
        iterations=5,
        location=[HERB_X, 0.0, 0.0],
        organs=[{"symbol": "L", "objects": ["herb_leaf"]}, {"symbol": "A", "objects": ["herb_flower"]}],
        limit=0,
    )
    cmd("assign_material", name="herb", material="stem")


def bush():
    for index, seed in enumerate(BUSH_SEEDS):
        name = f"bush_{index + 1}"
        cmd(
            "lsystem",
            name=name,
            preset="stochastic_1_27_leafy",
            seed=seed,
            location=[BUSH_X + (index - 1) * BUSH_GAP, 0.0, 0.0],
            organs=[{"symbol": "L", "objects": ["bush_leaf"]}, {"symbol": "K", "objects": ["bush_flower"]}],
            limit=0,
        )
        cmd("assign_material", name=name, material="stem")


def tree():
    cmd(
        "lsystem",
        name="tree",
        preset="monopodial_2_6a",
        location=[TREE_X, 0.0, 0.0],
        width=0.02,
        organs=[{"symbol": "B", "objects": ["tree_leaf"], "scale_by_parameter": True}, {"symbol": "C", "objects": ["tree_leaf"], "scale_by_parameter": True}],
        limit=0,
    )
    cmd("assign_material", name="tree", material="bark")


def fern():
    cmd(
        "lsystem",
        name="fern",
        preset="compound_leaf_5_11b",
        location=[FERN_X, 0.0, 0.0],
        organs=[{"symbol": "A", "objects": ["fern_leaflet"]}, {"symbol": "B", "objects": ["fern_leaflet"]}],
        limit=0,
    )
    cmd("assign_material", name="fern", material="stem")


def shots():
    views = {
        "herb": ([HERB_X, 0.0, 0.55], 1.7, [0.0, -1.0, 0.2]),
        "bushes": ([BUSH_X, 0.0, 0.55], 3.2, [0.0, -1.0, 0.2]),
        "tree": ([TREE_X, 0.0, 3.8], 9.5, [0.0, -1.0, 0.1]),
        "fern": ([FERN_X, 0.0, 0.3], 0.8, [0.0, -1.0, 0.1]),
        "overview": ([3.5, 0.0, 1.8], 22.0, [0.0, -1.0, 0.35]),
    }
    for name, (point, width, direction) in views.items():
        result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading="shaded", resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
        with open(os.path.join(OUT, f"{name}.png"), "wb") as handle:
            handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    cmd("new_scene")
    materials()
    ground()
    flower("herb_flower", 0.07, "petal_yellow", 9)
    leaf("herb_leaf", 0.085, "leaf")
    flower("bush_flower", 0.1, "petal_pink", 7)
    leaf("bush_leaf", 0.05, "leaf")
    leaf("tree_leaf", 1.6, "leaf")
    leaf("fern_leaflet", 0.022, "fern_leaf", leaflet_profile, 0.05)
    herb()
    bush()
    tree()
    fern()
    cmd("save_blend", path="lsystem-plants.blend")
    cmd("export", path="lsystem-plants.glb", names=["herb", "bush_1", "bush_2", "bush_3", "tree", "fern"])
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


main()
