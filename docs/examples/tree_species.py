import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "bridge"))

from blendworks_bridge import Handler

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.getcwd(), "tree-species"))
DEVICE = os.environ.get("BLENDWORKS_DEVICE", "auto")
SHOT_SIZE = int(os.environ.get("BLENDWORKS_SHOT_SIZE", "900"))
SHOT_SAMPLES = int(os.environ.get("BLENDWORKS_SHOT_SAMPLES", "48"))
DETAIL = float(os.environ.get("BLENDWORKS_TREE_DETAIL", "1.0"))
HDRI = os.environ.get("BLENDWORKS_HDRI")
SCANNED_BARK = os.environ.get("BLENDWORKS_SCANNED_BARK")
MEASURE = os.environ.get("BLENDWORKS_MEASURE_CROWNS", "1") == "1"
SPACING = 26.0
SPECIES = ("oak", "birch", "pine", "willow", "maple", "olive")
SEEDS = {"oak": 3, "birch": 5, "pine": 2, "willow": 7, "maple": 4, "olive": 6}
LEVELS = {"birch": [40, 12, 5], "pine": [26, 14, 7], "willow": [14, 64, 2]}
POINTS = {"oak": 6000, "maple": 3400, "olive": 2400}
BARK_MAPS = {"base_color": ("diff", "srgb"), "roughness": ("rough", "non_color"), "normal": ("nor_gl", "non_color"), "height": ("disp", "non_color")}
HANDLER = None
LOG = []
LOADED = set()
KEPT = ("name", "preset", "species", "nodes", "tips", "height", "spread", "pipe_error", "triangles", "manifold", "shells", "leaves", "clusters", "material", "variation", "foliage", "crown")


def cmd(name, /, **args):
    started = time.perf_counter()
    reply = HANDLER.handle({"cmd": name, "args": args})
    if not reply["ok"]:
        raise RuntimeError(f"{name}: {reply['error']['message']}")
    result = reply["result"]
    entry = {"cmd": name, "seconds": round(time.perf_counter() - started, 3)}
    entry.update({key: result[key] for key in KEPT if key in result})
    if name == "grow_tree":
        entry["strands"] = result["growth"]["strands"]
    LOG.append(entry)
    return result


def place(index):
    return [(index - 2.5) * SPACING, 0.0, 0.0]


def detail_args(species, detail):
    if species in POINTS:
        return {"points": max(50, int(round(POINTS[species] * detail)))}
    first, *rest = LEVELS[species]
    return {"branches": [max(4, int(round(first * detail)))] + rest}


def grow(send=None, detail=None):
    send = send or cmd
    detail = DETAIL if detail is None else detail
    for index, species in enumerate(SPECIES):
        extra = detail_args(species, detail) if detail < 1.0 else {}
        send("grow_tree", name=species, preset=species, seed=SEEDS[species], location=place(index), limit=0, **extra)


def bark_folders():
    folders = {}
    for entry in (SCANNED_BARK or "").split(";"):
        if not entry:
            continue
        species, _, folder = entry.rpartition("=")
        for name in [species] if species else SPECIES:
            folders.setdefault(name, folder)
    return folders


def scanned_bark(folder):
    asset = os.path.basename(folder.rstrip("/\\"))
    material = f"scanned_{asset}"
    if material not in LOADED:
        names = {}
        for channel, (suffix, space) in BARK_MAPS.items():
            image = f"{asset}_{suffix}"
            cmd("image_load", path=os.path.join(folder, f"{asset}_{suffix}_2k.jpg"), name=image, colorspace=space)
            names[channel] = image
        cmd("material_pbr", name=material, scale=[1.0, 1.0], **names)
        LOADED.add(material)
    return {"bark_material": material}


def dress(send=None, min_radius=None):
    send = send or cmd
    folders = bark_folders() if send is cmd else {}
    for species in SPECIES:
        mesh = scanned_bark(folders[species]) if species in folders else {}
        if min_radius is not None:
            mesh["min_radius"] = min_radius
        send("tree_mesh", name=species, **mesh)
    for species in SPECIES:
        send("tree_leaves", name=f"{species}_bark", leaves_name=f"{species}_leaves", seed=SEEDS[species], measure=MEASURE, **({"detail": "low"} if DETAIL < 1.0 else {}))


def lighting():
    if HDRI:
        cmd("set_world_hdri", path=HDRI, strength=1.0)
    cmd("add_primitive", type="plane", name="ground", size=8.0 * SPACING)
    cmd("material_procedural", name="soil", soil={"moisture": 0.4})
    cmd("assign_material", name="ground", material="soil")


def shots():
    for index, species in enumerate(SPECIES):
        tree = next(entry for entry in LOG if entry["cmd"] == "grow_tree" and entry["name"] == species)
        x = place(index)[0]
        height, spread = tree["height"], tree["spread"]
        views = {
            "mid": ([x, 0.0, 0.5 * height], 1.25 * max(height, 2.0 * spread), [0.3, -1.0, 0.05]),
            "close": ([x + 0.35 * spread, -0.4 * spread, 0.6 * height], 0.3 * height, [0.3, -1.0, 0.1]),
        }
        for view, (point, width, direction) in views.items():
            result = cmd("render_preview", focus={"point": point, "width": width, "direction": direction}, shading="shaded", resolution=SHOT_SIZE, samples=SHOT_SAMPLES, device=DEVICE)
            with open(os.path.join(OUT, f"{species}_{view}.png"), "wb") as handle:
                handle.write(base64.b64decode(result["images"][0]["data"]))


def main():
    global HANDLER
    os.makedirs(OUT, exist_ok=True)
    HANDLER = Handler(OUT, allow_python=False, desktop=False)
    cmd("new_scene")
    grow()
    dress()
    cmd("save_blend", path="tree-species.blend")
    lighting()
    shots()
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as handle:
        json.dump(LOG, handle, indent=1)
    print(json.dumps({"seconds": round(sum(entry["seconds"] for entry in LOG), 1), "commands": len(LOG)}))


if __name__ == "__main__":
    main()
